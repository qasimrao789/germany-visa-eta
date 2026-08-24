from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


TRACKER_URL = (
    "https://visatracker.waleedingermany.com/"
    "?consulate=islamabad_consulate"
)

PAKISTAN_TZ = ZoneInfo("Asia/Karachi")
DATE_FMT = "%d-%b-%Y"

BUFFER_PEOPLE = 50
RECENT_WINDOW_DAYS = 14


def clean(text: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        text.replace("\xa0", " "),
    ).strip()


def parse_date(text: str):
    text = clean(text)

    if not text:
        return None

    if text.lower() in {
        "-",
        "—",
        "none",
        "nan",
    }:
        return None

    return datetime.strptime(
        text,
        DATE_FMT,
    ).date()


def fetch_applicants():

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "AppleWebKit/537.36 "
            "Chrome/126 Safari/537.36 "
            "CommunityVisaETA/1.0"
        ),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    response = requests.get(
        TRACKER_URL,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    target_table = None
    header_names = []

    for table in soup.find_all("table"):

        headers = [
            clean(
                th.get_text(
                    " ",
                    strip=True,
                )
            )
            for th in table.find_all("th")
        ]

        if (
            "Joining Date" in headers
            and
            "Got Submission" in headers
        ):
            target_table = table
            header_names = headers
            break

    if target_table is None:
        raise RuntimeError(
            "Could not find the VisaTracker applicant table."
        )

    index = {
        name: i
        for i, name in enumerate(header_names)
    }

    required = [
        "#",
        "Joining Date",
        "Got Submission",
    ]

    missing = [
        column
        for column in required
        if column not in index
    ]

    if missing:
        raise RuntimeError(
            f"Missing table columns: {missing}"
        )

    applicants = []

    for row in target_table.find_all("tr"):

        cells_raw = row.find_all("td")

        if not cells_raw:
            continue

        cells = [
            clean(
                cell.get_text(
                    " ",
                    strip=True,
                )
            )
            for cell in cells_raw
        ]

        if len(cells) <= max(
            index[column]
            for column in required
        ):
            continue

        row_number = cells[
            index["#"]
        ]

        if not row_number.isdigit():
            continue

        joining_date = parse_date(
            cells[index["Joining Date"]]
        )

        if joining_date is None:
            continue

        submission_date = parse_date(
            cells[index["Got Submission"]]
        )

        applicants.append(
            {
                "joining_date": joining_date,
                "submission_date": submission_date,
            }
        )

    if not applicants:
        raise RuntimeError(
            "No applicants were parsed."
        )

    return applicants


def main():

    now_pk = datetime.now(
        PAKISTAN_TZ
    )

    today_pk = now_pk.date()

    applicants = fetch_applicants()

    waiting_by_join_date = Counter()
    submissions_by_date = Counter()

    joining_dates_with_submission = []

    all_joining_dates = []

    for applicant in applicants:

        joining_date = applicant[
            "joining_date"
        ]

        submission_date = applicant[
            "submission_date"
        ]

        all_joining_dates.append(
            joining_date
        )

        if submission_date is None:

            waiting_by_join_date[
                joining_date
            ] += 1

        else:

            submissions_by_date[
                submission_date
            ] += 1

            joining_dates_with_submission.append(
                joining_date
            )

    if not submissions_by_date:
        raise RuntimeError(
            "No reported submission dates exist."
        )

    payload = {

        "schema_version": 1,

        "consulate":
            "Islamabad",

        "as_of_date":
            today_pk.isoformat(),

        "generated_at":
            now_pk.isoformat(),

        "source_url":
            TRACKER_URL,

        "total_applicants":
            len(applicants),

        "total_reported_waiting":
            sum(
                waiting_by_join_date.values()
            ),

        "total_with_submission":
            sum(
                submissions_by_date.values()
            ),

        "first_submission_date":
            min(
                submissions_by_date
            ).isoformat(),

        "latest_submission_date":
            max(
                submissions_by_date
            ).isoformat(),

        "furthest_joining_date_with_submission":
            max(
                joining_dates_with_submission
            ).isoformat(),

        "minimum_joining_date":
            min(
                all_joining_dates
            ).isoformat(),

        "maximum_joining_date":
            max(
                all_joining_dates
            ).isoformat(),

        "buffer_people":
            BUFFER_PEOPLE,

        "recent_window_days":
            RECENT_WINDOW_DAYS,

        "waiting_by_join_date": {
            day.isoformat(): count
            for day, count
            in sorted(
                waiting_by_join_date.items()
            )
        },

        "submissions_by_date": {
            day.isoformat(): count
            for day, count
            in sorted(
                submissions_by_date.items()
            )
        },
    }

    output = Path(
        "data/tracker.json"
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        f"Applicants: "
        f"{payload['total_applicants']}"
    )

    print(
        f"Reported waiting: "
        f"{payload['total_reported_waiting']}"
    )

    print(
        f"Reported submissions: "
        f"{payload['total_with_submission']}"
    )

    print(
        "Furthest joining date with "
        f"submission: "
        f"{payload['furthest_joining_date_with_submission']}"
    )

    print(
        f"Created: {output}"
    )


if __name__ == "__main__":
    main()
