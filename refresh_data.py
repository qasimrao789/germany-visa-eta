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
    "data/historical_processing_v3.json"
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
        "n/a",
    }:
        return None

    formats = (
        "%d-%b-%Y",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
    )

    for fmt in formats:
        try:
            return datetime.strptime(
                text,
                fmt,
            ).date()
        except ValueError:
            pass

    raise ValueError(
        f"Unrecognized date format: {text!r}"
    )


# ============================================================
# HISTORICAL V3 DATA
# ============================================================

def require_non_negative_int(
    value,
    label: str,
) -> int:

    if (
        isinstance(value, bool)
        or
        not isinstance(value, int)
        or
        value < 0
    ):
        raise RuntimeError(
            f"{label} must be a non-negative integer."
        )

    return value


def load_historical_data():
    """
    Load and validate Historical V3.

    V3 consists of:
    1. Observed weekly totals for 26 Jan through 17 May 2026.
    2. One explicitly imputed four-day bridge, 18-21 May 2026.
    3. Observed daily counts for 22 May through 9 Aug 2026.

    For compatibility with the existing website JavaScript,
    the weekly totals are represented in submissions_by_date
    on each weekly period's final day. The other six days are
    zero. This does NOT claim those submissions occurred on
    that exact day; it only preserves the weekly total while
    keeping every calendar day in the long-term denominator.

    The recent 14-day speed is unaffected because the weekly
    history is far outside the recent window.
    """

    if not HISTORICAL_DATA_PATH.exists():
        raise RuntimeError(
            "Historical V3 data file is missing: "
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
            "Could not read Historical V3 data."
        ) from exc

    if raw.get(
        "methodology_version"
    ) != "historical-v3":
        raise RuntimeError(
            "Historical data file is not V3."
        )

    weekly_raw = raw.get(
        "weekly_history"
    )

    imputed_raw = raw.get(
        "imputed_period"
    )

    daily_raw = raw.get(
        "daily_history"
    )

    if not isinstance(
        weekly_raw,
        list,
    ) or not weekly_raw:
        raise RuntimeError(
            "Historical V3 must contain weekly_history."
        )

    if not isinstance(
        imputed_raw,
        dict,
    ):
        raise RuntimeError(
            "Historical V3 must contain imputed_period."
        )

    if not isinstance(
        daily_raw,
        dict,
    ):
        raise RuntimeError(
            "Historical V3 must contain daily_history."
        )

    # --------------------------------------------------------
    # 1. VALIDATE WEEKLY OBSERVED HISTORY
    # --------------------------------------------------------

    weekly_periods = []

    previous_end = None

    weekly_total = 0

    for index, row in enumerate(
        weekly_raw,
        start=1,
    ):

        if not isinstance(
            row,
            dict,
        ):
            raise RuntimeError(
                f"Weekly row {index} is invalid."
            )

        try:
            reported_on = date.fromisoformat(
                row[
                    "reported_on"
                ]
            )

            period_start = date.fromisoformat(
                row[
                    "period_start"
                ]
            )

            period_end = date.fromisoformat(
                row[
                    "period_end"
                ]
            )

        except Exception as exc:
            raise RuntimeError(
                f"Weekly row {index} contains "
                "an invalid date."
            ) from exc

        submissions = require_non_negative_int(
            row.get(
                "submissions"
            ),
            f"Weekly row {index} submissions",
        )

        if row.get(
            "status"
        ) != "observed":
            raise RuntimeError(
                f"Weekly row {index} must be observed."
            )

        if (
            period_end
            -
            period_start
        ).days != 6:
            raise RuntimeError(
                f"Weekly row {index} is not "
                "a seven-day period."
            )

        if (
            reported_on
            !=
            period_end
            +
            timedelta(
                days=1
            )
        ):
            raise RuntimeError(
                f"Weekly row {index} report date "
                "must be the Monday after period_end."
            )

        if period_start.weekday() != 0:
            raise RuntimeError(
                f"Weekly row {index} must start Monday."
            )

        if period_end.weekday() != 6:
            raise RuntimeError(
                f"Weekly row {index} must end Sunday."
            )

        if (
            previous_end is not None
            and
            period_start
            !=
            previous_end
            +
            timedelta(
                days=1
            )
        ):
            raise RuntimeError(
                "Weekly history contains a gap "
                "or overlap before "
                f"{period_start.isoformat()}."
            )

        previous_end = period_end

        weekly_total += submissions

        weekly_periods.append(
            {
                "start":
                    period_start,

                "end":
                    period_end,

                "submissions":
                    submissions,
            }
        )

    weekly_start = weekly_periods[
        0
    ][
        "start"
    ]

    weekly_end = weekly_periods[
        -1
    ][
        "end"
    ]

    # --------------------------------------------------------
    # 2. VALIDATE EXPLICITLY IMPUTED BRIDGE
    # --------------------------------------------------------

    try:
        imputed_start = date.fromisoformat(
            imputed_raw[
                "period_start"
            ]
        )

        imputed_end = date.fromisoformat(
            imputed_raw[
                "period_end"
            ]
        )

    except Exception as exc:
        raise RuntimeError(
            "Imputed period contains an invalid date."
        ) from exc

    imputed_submissions = require_non_negative_int(
        imputed_raw.get(
            "estimated_submissions"
        ),
        "Imputed submissions",
    )

    if imputed_raw.get(
        "status"
    ) != "imputed":
        raise RuntimeError(
            "The bridge period must be explicitly "
            "marked as imputed."
        )

    if (
        imputed_start
        !=
        weekly_end
        +
        timedelta(
            days=1
        )
    ):
        raise RuntimeError(
            "Imputed period does not start "
            "immediately after weekly history."
        )

    if (
        imputed_end
        <
        imputed_start
    ):
        raise RuntimeError(
            "Imputed period end is before its start."
        )

    # --------------------------------------------------------
    # 3. VALIDATE OBSERVED DAILY HISTORY
    # --------------------------------------------------------

    daily_counts_raw = daily_raw.get(
        "daily_counts"
    )

    if not isinstance(
        daily_counts_raw,
        dict,
    ) or not daily_counts_raw:
        raise RuntimeError(
            "daily_history.daily_counts is missing."
        )

    daily_counts = Counter()

    for day_text, count in daily_counts_raw.items():

        try:
            day = date.fromisoformat(
                day_text
            )
        except Exception as exc:
            raise RuntimeError(
                "Invalid daily historical date: "
                f"{day_text!r}"
            ) from exc

        daily_counts[
            day
        ] = require_non_negative_int(
            count,
            "Daily historical count "
            f"for {day_text}",
        )

    daily_start = min(
        daily_counts
    )

    daily_end = max(
        daily_counts
    )

    expected_daily_days = (
        daily_end
        -
        daily_start
    ).days + 1

    if len(
        daily_counts
    ) != expected_daily_days:

        missing = []

        current = daily_start

        while current <= daily_end:

            if current not in daily_counts:
                missing.append(
                    current.isoformat()
                )

            current += timedelta(
                days=1
            )

        raise RuntimeError(
            "Observed daily history has missing "
            "calendar dates: "
            + ", ".join(
                missing[:10]
            )
        )

    if (
        daily_start
        !=
        imputed_end
        +
        timedelta(
            days=1
        )
    ):
        raise RuntimeError(
            "Observed daily history does not start "
            "immediately after the imputed bridge."
        )

    daily_total = sum(
        daily_counts.values()
    )

    if (
        daily_raw.get(
            "historical_start"
        )
        !=
        daily_start.isoformat()
    ):
        raise RuntimeError(
            "Daily historical_start metadata mismatch."
        )

    if (
        daily_raw.get(
            "historical_end"
        )
        !=
        daily_end.isoformat()
    ):
        raise RuntimeError(
            "Daily historical_end metadata mismatch."
        )

    if (
        daily_raw.get(
            "historical_submissions"
        )
        !=
        daily_total
    ):
        raise RuntimeError(
            "Daily historical total metadata mismatch."
        )

    # --------------------------------------------------------
    # 4. BUILD A CONTINUOUS DAILY-COMPATIBLE HISTORY
    # --------------------------------------------------------

    historical_start = weekly_start

    historical_end = daily_end

    daily_compatible = Counter()

    current = historical_start

    while current <= historical_end:
        daily_compatible[
            current
        ] = 0

        current += timedelta(
            days=1
        )

    # Weekly totals are stored on the weekly period end only.
    # This preserves the exact weekly total without inventing
    # a fake daily distribution.
    for period in weekly_periods:

        daily_compatible[
            period[
                "end"
            ]
        ] += period[
            "submissions"
        ]

    # The only estimated quantity in V3.
    daily_compatible[
        imputed_end
    ] += imputed_submissions

    # Exact observed daily data takes over from 22 May onward.
    for day, count in daily_counts.items():

        daily_compatible[
            day
        ] = count

    historical_total = sum(
        daily_compatible.values()
    )

    expected_total = (
        weekly_total
        +
        imputed_submissions
        +
        daily_total
    )

    if historical_total != expected_total:
        raise RuntimeError(
            "Historical V3 total failed internal "
            "cross-check."
        )

    summary = raw.get(
        "summary",
        {},
    )

    if summary.get(
        "weekly_observed_submissions"
    ) != weekly_total:
        raise RuntimeError(
            "Weekly summary total mismatch."
        )

    if summary.get(
        "historical_imputed_submissions"
    ) != imputed_submissions:
        raise RuntimeError(
            "Imputed summary total mismatch."
        )

    if summary.get(
        "daily_observed_submissions"
    ) != daily_total:
        raise RuntimeError(
            "Daily summary total mismatch."
        )

    if summary.get(
        "historical_total_including_imputation"
    ) != historical_total:
        raise RuntimeError(
            "Historical V3 summary total mismatch."
        )

    historical_days = (
        historical_end
        -
        historical_start
    ).days + 1

    return {
        "daily_counts":
            daily_compatible,

        "start":
            historical_start,

        "end":
            historical_end,

        "total":
            historical_total,

        "days":
            historical_days,

        "weekly_observed_total":
            weekly_total,

        "weekly_observed_weeks":
            len(
                weekly_periods
            ),

        "imputed_total":
            imputed_submissions,

        "imputed_start":
            imputed_start,

        "imputed_end":
            imputed_end,

        "daily_observed_total":
            daily_total,

        "daily_observed_start":
            daily_start,
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
            "CommunityVisaETA/3.0"
        ),

        "Cache-Control":
            "no-cache",

        "Pragma":
            "no-cache",
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

        headers_found = [
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
            in headers_found

            and

            "Got Submission"
            in headers_found
        ):

            target_table = table

            header_names = headers_found

            break


    if target_table is None:

        raise RuntimeError(
            "Could not find the "
            "VisaTracker applicant table."
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

        if column
        not in index
    ]


    if missing:

        raise RuntimeError(
            f"Missing tracker columns: {missing}"
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
            index[
                "#"
            ]
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
            "No applicants were parsed "
            "from VisaTracker."
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
            "Historical V3 must end before today "
            "so live VisaTracker data can take over."
        )


    applicants = fetch_applicants()


    waiting_by_join_date = Counter()


    # Only submission dates AFTER historical_end are used
    # from the live tracker. Any current live row whose
    # Got Submission date is on/before historical_end is
    # intentionally ignored for speed history so it cannot
    # double-count the historical dataset.
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
    # BUILD ONE CONTINUOUS PROCESSING HISTORY
    #
    # 26 Jan -> 17 May:
    # observed weekly totals
    #
    # 18 May -> 21 May:
    # explicit imputation = 13
    #
    # 22 May -> 9 Aug:
    # observed daily data
    #
    # 10 Aug -> today:
    # fresh live VisaTracker
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
            3,

        "methodology_version":
            "historical-v3",

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

        "total_with_submission":
            live_with_submission,


        # ----------------------------------------------------
        # HISTORICAL V3 SOURCE SUMMARY
        # ----------------------------------------------------

        "processing_history_start":
            historical_start.isoformat(),

        "historical_data_end":
            historical_end.isoformat(),

        "historical_weekly_observed_weeks":
            historical[
                "weekly_observed_weeks"
            ],

        "historical_weekly_observed_submissions":
            historical[
                "weekly_observed_total"
            ],

        "historical_imputed_period_start":
            historical[
                "imputed_start"
            ].isoformat(),

        "historical_imputed_period_end":
            historical[
                "imputed_end"
            ].isoformat(),

        "historical_imputed_submissions":
            historical[
                "imputed_total"
            ],

        "historical_daily_observed_start":
            historical[
                "daily_observed_start"
            ].isoformat(),

        "historical_daily_observed_submissions":
            historical[
                "daily_observed_total"
            ],

        "historical_submission_count":
            historical[
                "total"
            ],

        "historical_calendar_days":
            historical[
                "days"
            ],


        # ----------------------------------------------------
        # COMBINED HISTORY THROUGH TODAY
        # ----------------------------------------------------

        # Keep this field for compatibility with app.js.
        # It represents the START of the available processing
        # history, even though early V3 values are weekly
        # aggregates rather than exact daily observations.
        "first_submission_date":
            historical_start.isoformat(),

        "latest_submission_date":
            max(
                positive_submission_days
            ).isoformat(),

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

        "historical_data_quality_note":
            (
                "V3 uses 16 observed weekly totals from "
                "26 Jan-17 May 2026, an explicitly imputed "
                "13 submissions for the missing 18-21 May "
                "bridge, observed daily counts from "
                "22 May-9 Aug 2026, and fresh live "
                "VisaTracker data from 10 Aug onward."
            ),


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
        # ANONYMOUS AGGREGATES USED BY WEBSITE
        # ----------------------------------------------------

        "waiting_by_join_date": {
            day.isoformat(): count

            for day, count
            in sorted(
                waiting_by_join_date.items()
            )
        },

        # The early weekly totals are represented on each
        # weekly period-end date only. This preserves their
        # exact total and the correct calendar-day denominator.
        # Recent 14-day calculations use fresh live dates.
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
        " HISTORICAL V3 TRACKER DATA CREATED"
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
        "Observed weekly history:",
        payload[
            "historical_weekly_observed_weeks"
        ],
        "weeks /",
        payload[
            "historical_weekly_observed_submissions"
        ],
        "submissions",
    )


    print(
        "Imputed bridge:",
        payload[
            "historical_imputed_period_start"
        ],
        "through",
        payload[
            "historical_imputed_period_end"
        ],
        "/",
        payload[
            "historical_imputed_submissions"
        ],
        "estimated submissions",
    )


    print(
        "Observed daily history begins:",
        payload[
            "historical_daily_observed_start"
        ],
    )


    print(
        "Observed daily submissions:",
        payload[
            "historical_daily_observed_submissions"
        ],
    )


    print(
        "Historical V3 total through",
        payload[
            "historical_data_end"
        ],
        ":",
        payload[
            "historical_submission_count"
        ],
    )


    print("")


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

