from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
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

HISTORICAL_DATA_PATH = Path(
    "data/historical_daily_counts.json"
)


# ============================================================
# TEXT / DATE HELPERS
# ============================================================

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


# ============================================================
# HISTORICAL DATA
# ============================================================

def load_historical_data():
    """
    Load and validate the anonymous historical daily counts.

    The file must contain one count for every calendar day in
    its historical period. This prevents gaps from silently
    distorting the long-term average.
    """

    if not HISTORICAL_DATA_PATH.exists():
        raise RuntimeError(
            "Historical data file is missing: "
            f"{HISTORICAL_DATA_PATH}"
        )

    try:
        raw = json.loads(
            HISTORICAL_DATA_PATH.read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:
        raise RuntimeError(
            "Could not read historical data file."
        ) from exc

    daily_raw = raw.get(
        "daily_counts"
    )

    if not isinstance(
        daily_raw,
        dict,
    ) or not daily_raw:
        raise RuntimeError(
            "Historical data must contain "
            "a non-empty daily_counts object."
        )

    daily_counts = Counter()

    for day_text, count in daily_raw.items():

        try:
            day = date.fromisoformat(
                day_text
            )
        except Exception as exc:
            raise RuntimeError(
                "Invalid historical date: "
                f"{day_text!r}"
            ) from exc

        if (
            isinstance(count, bool)
            or
            not isinstance(count, int)
            or
            count < 0
        ):
            raise RuntimeError(
                "Invalid historical submission count "
                f"for {day_text}: {count!r}"
            )

        daily_counts[
            day
        ] = count

    historical_start = min(
        daily_counts
    )

    historical_end = max(
        daily_counts
    )

    # --------------------------------------------------------
    # Require every calendar day to be present.
    # Zero-submission days are part of the denominator.
    # --------------------------------------------------------

    expected_days = (
        historical_end
        -
        historical_start
    ).days + 1

    if len(
        daily_counts
    ) != expected_days:

        missing = []

        current = historical_start

        while current <= historical_end:

            if current not in daily_counts:
                missing.append(
                    current.isoformat()
                )

            current += timedelta(
                days=1
            )

        raise RuntimeError(
            "Historical data has missing calendar "
            "dates: "
            + ", ".join(
                missing[:10]
            )
        )

    historical_total = sum(
        daily_counts.values()
    )

    # --------------------------------------------------------
    # Cross-check the metadata inside the JSON file.
    # --------------------------------------------------------

    declared_start = raw.get(
        "historical_start"
    )

    declared_end = raw.get(
        "historical_end"
    )

    declared_total = raw.get(
        "historical_submissions"
    )

    if (
        declared_start
        != historical_start.isoformat()
    ):
        raise RuntimeError(
            "historical_start metadata does not "
            "match daily_counts."
        )

    if (
        declared_end
        != historical_end.isoformat()
    ):
        raise RuntimeError(
            "historical_end metadata does not "
            "match daily_counts."
        )

    if (
        declared_total
        != historical_total
    ):
        raise RuntimeError(
            "historical_submissions metadata does "
            "not match the sum of daily_counts."
        )

    return {
        "daily_counts":
            daily_counts,

        "start":
            historical_start,

        "end":
            historical_end,

        "total":
            historical_total,

        "days":
            expected_days,
    }


# ============================================================
# LIVE VISATRACKER
# ============================================================

def fetch_applicants():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "AppleWebKit/537.36 "
            "Chrome/126 Safari/537.36 "
            "CommunityVisaETA/2.0"
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

    for table in soup.find_all(
        "table"
    ):

        headers = [
            clean(
                th.get_text(
                    " ",
                    strip=True,
                )
            )
            for th
            in table.find_all(
                "th"
            )
        ]

        if (
            "Joining Date"
            in headers
            and
            "Got Submission"
            in headers
        ):
            target_table = table
            header_names = headers
            break

    if target_table is None:
        raise RuntimeError(
            "Could not find the VisaTracker "
            "applicant table."
        )

    index = {
        name: i
        for i, name
        in enumerate(
            header_names
        )
    }

    required = [
        "#",
        "Joining Date",
        "Got Submission",
    ]

    missing = [
        column
        for column
        in required
        if column not in index
    ]

    if missing:
        raise RuntimeError(
            f"Missing table columns: {missing}"
        )

    max_required_index = max(
        index[
            column
        ]
        for column
        in required
    )

    applicants = []

    for row in target_table.find_all(
        "tr"
    ):

        cells_raw = row.find_all(
            "td"
        )

        if not cells_raw:
            continue

        cells = [
            clean(
                cell.get_text(
                    " ",
                    strip=True,
                )
            )
            for cell
            in cells_raw
        ]

        if (
            len(cells)
            <=
            max_required_index
        ):
            continue

        row_number = cells[
            index["#"]
        ]

        if not row_number.isdigit():
            continue

        joining_date = parse_date(
            cells[
                index[
                    "Joining Date"
                ]
            ]
        )

        if joining_date is None:
            continue

        submission_date = parse_date(
            cells[
                index[
                    "Got Submission"
                ]
            ]
        )

        applicants.append(
            {
                "joining_date":
                    joining_date,

                "submission_date":
                    submission_date,
            }
        )

    if not applicants:
        raise RuntimeError(
            "No applicants were parsed."
        )

    return applicants


# ============================================================
# MAIN
# ============================================================

def main():

    now_pk = datetime.now(
        PAKISTAN_TZ
    )

    today_pk = now_pk.date()

    historical = (
        load_historical_data()
    )

    historical_start = historical[
        "start"
    ]

    historical_end = historical[
        "end"
    ]

    if historical_end >= today_pk:
        raise RuntimeError(
            "Historical data must end before "
            "today so the live tracker can take "
            "over after the historical period."
        )

    applicants = fetch_applicants()

    waiting_by_join_date = Counter()

    # Only live submission dates AFTER the historical
    # period are used for processing-speed history.
    # Anything on/before historical_end is intentionally
    # ignored here to prevent double-counting.
    live_submissions_after_history = Counter()

    joining_dates_with_submission = []

    all_joining_dates = []

    live_with_submission = 0

    ignored_overlapping_live_submissions = 0

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

        # ----------------------------------------------------
        # Blank or future submission dates remain unresolved.
        # ----------------------------------------------------

        if (
            submission_date is None
            or
            submission_date > today_pk
        ):

            waiting_by_join_date[
                joining_date
            ] += 1

            continue

        live_with_submission += 1

        joining_dates_with_submission.append(
            joining_date
        )

        if (
            submission_date
            >
            historical_end
        ):

            live_submissions_after_history[
                submission_date
            ] += 1

        else:

            ignored_overlapping_live_submissions += 1

    # ========================================================
    # BUILD ONE CONTINUOUS DAILY PROCESSING HISTORY
    #
    # Historical file:
    #   historical_start ... historical_end
    #
    # Live VisaTracker:
    #   historical_end + 1 ... today
    #
    # This guarantees there is never any overlap/double count.
    # ========================================================

    submissions_by_date = Counter()

    current = historical_start

    while current <= today_pk:

        if current <= historical_end:

            submissions_by_date[
                current
            ] = historical[
                "daily_counts"
            ][
                current
            ]

        else:

            submissions_by_date[
                current
            ] = (
                live_submissions_after_history[
                    current
                ]
            )

        current += timedelta(
            days=1
        )

    total_processing_history_submissions = sum(
        submissions_by_date.values()
    )

    positive_submission_days = [
        day
        for day, count
        in submissions_by_date.items()
        if count > 0
    ]

    if not positive_submission_days:
        raise RuntimeError(
            "No submission activity exists "
            "in the combined processing history."
        )

    processing_history_days = (
        today_pk
        -
        historical_start
    ).days + 1

    long_term_speed = (
        total_processing_history_submissions
        /
        processing_history_days
    )

    live_period_start = (
        historical_end
        +
        timedelta(
            days=1
        )
    )

    payload = {

        "schema_version":
            2,

        "methodology_version":
            "historical-v2",

        "consulate":
            "Islamabad",

        "as_of_date":
            today_pk.isoformat(),

        "generated_at":
            now_pk.isoformat(),

        "source_url":
            TRACKER_URL,

        # ----------------------------------------------------
        # CURRENT LIVE TRACKER
        # ----------------------------------------------------

        "total_applicants":
            len(
                applicants
            ),

        "total_reported_waiting":
            sum(
                waiting_by_join_date.values()
            ),

        # Preserve the old meaning of this field:
        # number of CURRENT VisaTracker entries that have
        # a valid Got Submission date.
        "total_with_submission":
            live_with_submission,

        # ----------------------------------------------------
        # COMBINED PROCESSING HISTORY
        # ----------------------------------------------------

        "first_submission_date":
            historical_start.isoformat(),

        "latest_submission_date":
            max(
                positive_submission_days
            ).isoformat(),

        "processing_history_start":
            historical_start.isoformat(),

        "historical_data_end":
            historical_end.isoformat(),

        "historical_submission_count":
            historical[
                "total"
            ],

        "historical_calendar_days":
            historical[
                "days"
            ],

        "live_processing_period_start":
            live_period_start.isoformat(),

        "live_submission_count_after_history":
            sum(
                live_submissions_after_history.values()
            ),

        "processing_history_submission_count":
            total_processing_history_submissions,

        "processing_history_calendar_days":
            processing_history_days,

        "calculated_long_term_speed":
            round(
                long_term_speed,
                6,
            ),

        "ignored_overlapping_live_submissions":
            ignored_overlapping_live_submissions,

        # ----------------------------------------------------
        # QUEUE MARKERS
        # ----------------------------------------------------

        "furthest_joining_date_with_submission":
            (
                max(
                    joining_dates_with_submission
                ).isoformat()

                if
                joining_dates_with_submission

                else
                None
            ),

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

        # ----------------------------------------------------
        # ANONYMOUS AGGREGATES USED BY THE WEBSITE
        # ----------------------------------------------------

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

    print("")
    print(
        "=============================================="
    )
    print(
        " HISTORICAL V2 TRACKER DATA CREATED"
    )
    print(
        "=============================================="
    )
    print("")

    print(
        "Current live applicants:",
        payload[
            "total_applicants"
        ],
    )

    print(
        "Current live waiting:",
        payload[
            "total_reported_waiting"
        ],
    )

    print(
        "Current live with submission:",
        payload[
            "total_with_submission"
        ],
    )

    print("")

    print(
        "Historical period:",
        f"{payload['processing_history_start']}"
        " through "
        f"{payload['historical_data_end']}",
    )

    print(
        "Historical submissions:",
        payload[
            "historical_submission_count"
        ],
    )

    print(
        "Live submissions after historical period:",
        payload[
            "live_submission_count_after_history"
        ],
    )

    print(
        "Combined processing-history submissions:",
        payload[
            "processing_history_submission_count"
        ],
    )

    print(
        "Combined processing-history calendar days:",
        payload[
            "processing_history_calendar_days"
        ],
    )

    print(
        "Long-term speed:",
        f"{payload['calculated_long_term_speed']:.2f}"
        " applicants/day",
    )

    print("")

    print(
        "Furthest joining date with submission:",
        payload[
            "furthest_joining_date_with_submission"
        ],
    )

    print(
        "Ignored overlapping live submissions:",
        payload[
            "ignored_overlapping_live_submissions"
        ],
    )

    print("")

    print(
        f"Created: {output}"
    )


if __name__ == "__main__":
    main()

