"""Ensure public Visa ETA scraper never builds estimates from partial pages."""

import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import refresh_data


def row(n, joining="01-Jan-2026", submitted=""):
    return (n, joining, submitted)


def page_html(rows, start=None, end=None, total=None):
    text = f"<p>{total} applicants</p>" if total is not None else ""
    if start is not None:
        text += f"<p>Showing {start} – {end} of {total}</p>"
    body = "".join(
        f"<tr><td>{n}</td><td>{joining}</td><td>{submitted}</td></tr>"
        for n, joining, submitted in rows
    )
    return (
        "<html><body>" + text
        + "<table><tr><th>#</th><th>Joining Date</th>"
        "<th>Got Submission</th></tr>"
        + body + "</table></body></html>"
    )


class Response:
    def __init__(self, html):
        self.text = html

    def raise_for_status(self):
        pass


def fake_requests(pages, visited):
    def get(url, **kwargs):
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        number = int(query["page"][0])
        visited.append((number, query["consulate"][0]))
        return Response(pages[number])
    return get


class PaginationTests(unittest.TestCase):
    def test_shortened_headers_and_spaced_dates(self):
        html = """
        <html><body>
        <p>1 applicants</p><p>Showing 1 – 1 of 1</p>
        <table><tr>
          <th>#</th><th>NAME</th><th>UNIVERSITY</th>
          <th>JOINED</th><th>GOT SUB.</th><th>SUBMITTED</th>
          <th>CORRECTION</th><th>APPOINTMENT</th><th>STAGE</th>
        </tr>
        <tr>
          <td>1</td><td>Sample Person</td><td>Example University</td>
          <td>24 Jan 2026</td><td>9 Oct 2026</td><td>10 Oct 2026</td>
          <td></td><td></td><td>Submitted</td>
        </tr></table></body></html>
        """
        rows, page_range, count = refresh_data._parse_applicant_page(html)
        self.assertEqual(page_range, (1, 1, 1))
        self.assertEqual(count, 1)
        self.assertEqual(rows[0][1]["joining_date"].isoformat(), "2026-01-24")
        self.assertEqual(rows[0][1]["submission_date"].isoformat(), "2026-10-09")
        self.assertEqual(
            refresh_data.canonical_header("Submitted"), "Submitted"
        )

    def test_original_header_still_supported(self):
        self.assertEqual(
            refresh_data.canonical_header("Joining Date"), "Joining Date"
        )
        self.assertEqual(
            refresh_data.canonical_header("Got Submission"), "Got Submission"
        )

    def test_multi_page_concatenates_anonymous_data(self):
        pages = {
            1: page_html([row(1), row(2)], 1, 2, 3),
            2: page_html([row(3, "27-Jun-2026", "09-Oct-2026")], 3, 3, 3),
        }
        visited = []
        with patch.object(refresh_data.requests, "get",
                          side_effect=fake_requests(pages, visited)):
            applicants = refresh_data.fetch_applicants()
        self.assertEqual(len(applicants), 3)
        self.assertEqual(
            visited,
            [(1, "islamabad_consulate"), (2, "islamabad_consulate")],
        )
        self.assertEqual(
            applicants[-1]["joining_date"].isoformat(), "2026-06-27"
        )
        self.assertEqual(
            applicants[-1]["submission_date"].isoformat(), "2026-10-09"
        )
        self.assertEqual(
            set(applicants[0].keys()), {"joining_date", "submission_date"}
        )

    def test_page_lengths_are_not_assumed_to_be_fifty(self):
        pages = {
            1: page_html([row(1)], 1, 1, 4),
            2: page_html([row(2), row(3)], 2, 3, 4),
            3: page_html([row(4)], 4, 4, 4),
        }
        with patch.object(refresh_data.requests, "get",
                          side_effect=fake_requests(pages, [])):
            self.assertEqual(len(refresh_data.fetch_applicants()), 4)

    def test_repeated_page_fails(self):
        pages = {
            1: page_html([row(1), row(2)], 1, 2, 4),
            2: page_html([row(1), row(2)], 1, 2, 4),
        }
        with patch.object(refresh_data.requests, "get",
                          side_effect=fake_requests(pages, [])):
            with self.assertRaisesRegex(RuntimeError, "missing, duplicated"):
                refresh_data.fetch_applicants()

    def test_missing_row_fails(self):
        page = page_html([row(1), row(3)], 1, 3, 3)
        with patch.object(refresh_data.requests, "get",
                          return_value=Response(page)):
            with self.assertRaisesRegex(RuntimeError, "missing, duplicated"):
                refresh_data.fetch_applicants()

    def test_changed_total_fails(self):
        pages = {
            1: page_html([row(1)], 1, 1, 3),
            2: page_html([row(2)], 2, 2, 4),
        }
        with patch.object(refresh_data.requests, "get",
                          side_effect=fake_requests(pages, [])):
            with self.assertRaisesRegex(RuntimeError, "total changed"):
                refresh_data.fetch_applicants()

    def test_legacy_single_page_works_with_verifiable_total(self):
        page = page_html([row(1), row(2)], total=2)
        with patch.object(refresh_data.requests, "get",
                          return_value=Response(page)):
            self.assertEqual(len(refresh_data.fetch_applicants()), 2)

    def test_incomplete_single_page_rejected(self):
        page = page_html([row(1)], total=50)
        with patch.object(refresh_data.requests, "get",
                          return_value=Response(page)):
            with self.assertRaisesRegex(RuntimeError, "Cannot verify"):
                refresh_data.fetch_applicants()

    def test_metadata_missing_rejected(self):
        page = page_html([row(1)])
        with patch.object(refresh_data.requests, "get",
                          return_value=Response(page)):
            with self.assertRaisesRegex(RuntimeError, "Cannot verify"):
                refresh_data.fetch_applicants()

    def test_missing_join_date_rejected(self):
        page = page_html([row(1, joining="")], 1, 1, 1)
        with patch.object(refresh_data.requests, "get",
                          return_value=Response(page)):
            with self.assertRaisesRegex(RuntimeError, "Joining Date"):
                refresh_data.fetch_applicants()

    def test_range_metadata_parses_comma_and_hyphen(self):
        page = page_html([row(1)], 1, 1, 1000).replace(
            "Showing 1 – 1 of 1000", "Showing 1-1 of 1,000"
        )
        _, page_range, _ = refresh_data._parse_applicant_page(page)
        self.assertEqual(page_range, (1, 1, 1000))


if __name__ == "__main__":
    unittest.main()
