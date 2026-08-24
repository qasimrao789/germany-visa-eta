let trackerData = null;


/* ============================================================
   CONSTANTS
============================================================ */

const MS_PER_DAY =
    24 * 60 * 60 * 1000;


/* ============================================================
   DATE HELPERS
============================================================ */

function parseISODate(value) {

    return new Date(
        `${value}T12:00:00Z`
    );
}


function toISODate(date) {

    return date
        .toISOString()
        .slice(0, 10);
}


function formatDate(value) {

    if (!value) {
        return "N/A";
    }

    const date =
        typeof value === "string"
            ? parseISODate(value)
            : value;

    return new Intl.DateTimeFormat(
        "en-GB",
        {
            day: "2-digit",
            month: "short",
            year: "numeric",
            timeZone: "UTC",
        }
    ).format(date);
}


/* ============================================================
   NUMBER OF CALENDAR DAYS
============================================================ */

function inclusiveDays(
    startISO,
    endISO
) {

    const start =
        parseISODate(startISO);

    const end =
        parseISODate(endISO);

    return (
        Math.floor(
            (end - start)
            /
            MS_PER_DAY
        )
        + 1
    );
}


/* ============================================================
   SUBTRACT DAYS
============================================================ */

function subtractDays(
    iso,
    count
) {

    const date =
        parseISODate(iso);

    date.setUTCDate(
        date.getUTCDate() - count
    );

    return toISODate(date);
}


/* ============================================================
   MAX DATE
============================================================ */

function maxDate(
    first,
    second
) {

    return first > second
        ? first
        : second;
}


/* ============================================================
   COUNT REPORTED SUBMISSIONS BETWEEN TWO DATES
============================================================ */

function sumSubmissions(
    startISO,
    endISO
) {

    let total = 0;

    for (
        const [day, count]
        of Object.entries(
            trackerData.submissions_by_date
        )
    ) {

        if (
            day >= startISO
            &&
            day <= endISO
        ) {

            total += count;
        }
    }

    return total;
}


/* ============================================================
   ADD MONDAY-FRIDAY BUSINESS DAYS
============================================================ */

function addBusinessDays(
    startISO,
    count
) {

    const date =
        parseISODate(startISO);

    let added = 0;

    while (added < count) {

        date.setUTCDate(
            date.getUTCDate() + 1
        );

        const weekday =
            date.getUTCDay();

        /*
        0 = Sunday
        6 = Saturday
        */

        if (
            weekday !== 0
            &&
            weekday !== 6
        ) {

            added += 1;
        }
    }

    return date;
}


/* ============================================================
   CALCULATE LONG-TERM AND RECENT PROCESSING SPEED
============================================================ */

function calculateSpeeds() {

    const asOf =
        trackerData.as_of_date;

    const first =
        trackerData.first_submission_date;


    /* --------------------------------------------------------
       LONG-TERM SPEED

       Total reported submissions
       divided by
       every calendar day from first submission through today.

       Saturdays, Sundays and zero-clearance days count.
    --------------------------------------------------------- */

    const longDays =
        inclusiveDays(
            first,
            asOf
        );

    const longTotal =
        sumSubmissions(
            first,
            asOf
        );

    const longSpeed =
        longTotal
        /
        longDays;


    /* --------------------------------------------------------
       RECENT 14-DAY SPEED
    --------------------------------------------------------- */

    const configuredWindow =
        trackerData.recent_window_days
        || 14;

    const proposedRecentStart =
        subtractDays(
            asOf,
            configuredWindow - 1
        );

    /*
    If submission reporting has existed for fewer
    than 14 days, start from the first submission date.
    */

    const recentStart =
        maxDate(
            first,
            proposedRecentStart
        );

    const recentDays =
        inclusiveDays(
            recentStart,
            asOf
        );

    const recentTotal =
        sumSubmissions(
            recentStart,
            asOf
        );

    const recentSpeed =
        recentTotal
        /
        recentDays;


    return {
        longSpeed,
        recentSpeed,
        recentDays,
    };
}


/* ============================================================
   COUNT PEOPLE STILL WAITING BEFORE USER'S JOINING DATE
============================================================ */

function countWaitingBefore(
    joiningDate
) {

    let total = 0;

    for (
        const [day, count]
        of Object.entries(
            trackerData.waiting_by_join_date
        )
    ) {

        if (
            day < joiningDate
        ) {

            total += count;
        }
    }

    return total;
}


/* ============================================================
   CALCULATE ETA FROM QUEUE SIZE AND PROCESSING SPEED
============================================================ */

function etaFromQueue(
    queue,
    speed
) {

    if (
        !speed
        ||
        speed <= 0
    ) {

        return null;
    }


    /*
    Queue divided by people cleared per day.
    */

    const estimatedDays =
        Math.ceil(
            queue / speed
        );


    /*
    Convert those estimated days into
    Monday-Friday business days.
    */

    const estimatedDate =
        addBusinessDays(
            trackerData.as_of_date,
            estimatedDays
        );


    return {

        businessDays:
            estimatedDays,

        date:
            estimatedDate,
    };
}


/* ============================================================
   RENDER QUEUE BREAKDOWN
============================================================ */

function renderBreakdown(
    elementId,
    peopleBefore,
    sameDayAhead,
    buffer,
    total
) {

    const element =
        document.getElementById(
            elementId
        );

    element.innerHTML = `

        <div class="breakdown-row">

            <span class="breakdown-number">
                ${peopleBefore}
            </span>

            <span class="breakdown-label">
                still waiting before your joining date
            </span>

        </div>


        <div class="operator">
            +
        </div>


        <div class="breakdown-row">

            <span class="breakdown-number">
                ${sameDayAhead}
            </span>

            <span class="breakdown-label">
                assumed ahead from your joining date
            </span>

        </div>


        <div class="operator">
            +
        </div>


        <div class="breakdown-row">

            <span class="breakdown-number">
                ${buffer}
            </span>

            <span class="breakdown-label">
                safety buffer for unreported applicants
            </span>

        </div>


        <div class="breakdown-total">

            <span>
                Estimated queue ahead
            </span>

            <strong>
                ${total}
            </strong>

        </div>
    `;
}


/* ============================================================
   MAIN CALCULATION
============================================================ */

function calculate() {

    const input =
        document.getElementById(
            "joiningDate"
        );

    const error =
        document.getElementById(
            "errorMessage"
        );

    const joiningDate =
        input.value;


    error.textContent = "";


    /* --------------------------------------------------------
       VALIDATION
    --------------------------------------------------------- */

    if (!joiningDate) {

        error.textContent =
            "Please select the date when you joined the waiting list.";

        return;
    }


    if (
        joiningDate
        >
        trackerData.as_of_date
    ) {

        error.textContent =
            "Your joining date cannot be in the future.";

        return;
    }


    /* --------------------------------------------------------
       SPEED
    --------------------------------------------------------- */

    const speeds =
        calculateSpeeds();


    /* --------------------------------------------------------
       PEOPLE BEFORE USER
    --------------------------------------------------------- */

    const before =
        countWaitingBefore(
            joiningDate
        );


    /* --------------------------------------------------------
       PEOPLE ON SAME DATE
    --------------------------------------------------------- */

    const sameDay =
        trackerData
            .waiting_by_join_date[
                joiningDate
            ]
        || 0;


    /* --------------------------------------------------------
       SAFETY BUFFER

       THIS IS THE +50 BUFFER.
    --------------------------------------------------------- */

    const buffer =
        trackerData.buffer_people
        || 50;


    /* ========================================================
       THREE SAME-DAY SCENARIOS
    ========================================================= */


    /* --------------------------------------------------------
       OPTIMISTIC

       Nobody from same date assumed ahead.
    --------------------------------------------------------- */

    const optimisticSameDayAhead =
        0;

    const optimisticQueue =
        before
        +
        optimisticSameDayAhead
        +
        buffer;


    /* --------------------------------------------------------
       MIDDLE

       Half of same-day unresolved applicants assumed ahead.
    --------------------------------------------------------- */

    const middleSameDayAhead =
        Math.floor(
            sameDay / 2
        );

    const middleQueue =
        before
        +
        middleSameDayAhead
        +
        buffer;


    /* --------------------------------------------------------
       CONSERVATIVE

       Everyone from same date assumed ahead.
    --------------------------------------------------------- */

    const conservativeSameDayAhead =
        sameDay;

    const conservativeQueue =
        before
        +
        conservativeSameDayAhead
        +
        buffer;


    /* ========================================================
       LONG-TERM ETAs
    ========================================================= */

    const optimisticETA =
        etaFromQueue(
            optimisticQueue,
            speeds.longSpeed
        );


    const middleETA =
        etaFromQueue(
            middleQueue,
            speeds.longSpeed
        );


    const conservativeETA =
        etaFromQueue(
            conservativeQueue,
            speeds.longSpeed
        );


    /* ========================================================
       RECENT-SPEED ETA

       Uses middle queue assumption.
    ========================================================= */

    const recentMiddleETA =
        etaFromQueue(
            middleQueue,
            speeds.recentSpeed
        );


    /* ========================================================
       DISPLAY MAIN ESTIMATE
    ========================================================= */

    document.getElementById(
        "primaryDate"
    ).textContent =
        formatDate(
            middleETA.date
        );


    /* ========================================================
       DISPLAY SPEEDS
    ========================================================= */

    document.getElementById(
        "longSpeed"
    ).textContent =
        `${speeds.longSpeed.toFixed(2)} applicants/day`;


    document.getElementById(
        "recentSpeed"
    ).textContent =
        `${speeds.recentSpeed.toFixed(2)} applicants/day`;


    /* ========================================================
       DISPLAY QUEUE COUNTS
    ========================================================= */

    document.getElementById(
        "peopleBefore"
    ).textContent =
        before;


    document.getElementById(
        "sameDay"
    ).textContent =
        sameDay;


    /* ========================================================
       OPTIMISTIC RESULT
    ========================================================= */

    document.getElementById(
        "optimisticDate"
    ).textContent =
        formatDate(
            optimisticETA.date
        );


    document.getElementById(
        "optimisticQueue"
    ).textContent =
        `${optimisticQueue} people estimated ahead`;


    renderBreakdown(
        "optimisticBreakdown",
        before,
        optimisticSameDayAhead,
        buffer,
        optimisticQueue
    );


    /* ========================================================
       MIDDLE RESULT
    ========================================================= */

    document.getElementById(
        "middleDate"
    ).textContent =
        formatDate(
            middleETA.date
        );


    document.getElementById(
        "middleQueue"
    ).textContent =
        `${middleQueue} people estimated ahead`;


    renderBreakdown(
        "middleBreakdown",
        before,
        middleSameDayAhead,
        buffer,
        middleQueue
    );


    /* ========================================================
       CONSERVATIVE RESULT
    ========================================================= */

    document.getElementById(
        "conservativeDate"
    ).textContent =
        formatDate(
            conservativeETA.date
        );


    document.getElementById(
        "conservativeQueue"
    ).textContent =
        `${conservativeQueue} people estimated ahead`;


    renderBreakdown(
        "conservativeBreakdown",
        before,
        conservativeSameDayAhead,
        buffer,
        conservativeQueue
    );


    /* ========================================================
       RECENT SPEED RESULT
    ========================================================= */

    document.getElementById(
        "recentExpectedDate"
    ).textContent =
        recentMiddleETA
            ?
            formatDate(
                recentMiddleETA.date
            )
            :
            "No recent processing activity";


    /* ========================================================
       TRACKER INFORMATION
    ========================================================= */

    document.getElementById(
        "queueReached"
    ).textContent =
        formatDate(
            trackerData
                .furthest_joining_date_with_submission
        );


    document.getElementById(
        "totalApplicants"
    ).textContent =
        trackerData.total_applicants;


    document.getElementById(
        "bufferPeople"
    ).textContent =
        `+${buffer} applicants`;


    document.getElementById(
        "lastUpdated"
    ).textContent =
        formatDate(
            trackerData.as_of_date
        );


    /* ========================================================
       SHOW RESULTS
    ========================================================= */

    document.getElementById(
        "results"
    ).classList.remove(
        "hidden"
    );


    document.getElementById(
        "results"
    ).scrollIntoView({
        behavior: "smooth",
        block: "start",
    });
}


/* ============================================================
   LOAD TRACKER JSON
============================================================ */

async function loadTrackerData() {

    const status =
        document.getElementById(
            "dataStatus"
        );

    try {

        /*
        Add timestamp to URL so browser does not
        accidentally use an old cached JSON file.
        */

        const response =
            await fetch(
                `./data/tracker.json?t=${Date.now()}`
            );


        if (!response.ok) {

            throw new Error(
                `HTTP ${response.status}`
            );
        }


        trackerData =
            await response.json();


        /* ----------------------------------------------------
           PREVENT FUTURE DATES
        ----------------------------------------------------- */

        const input =
            document.getElementById(
                "joiningDate"
            );

        input.max =
            trackerData.as_of_date;


        /* ----------------------------------------------------
           STATUS
        ----------------------------------------------------- */

        status.textContent =
            `Community data loaded successfully. `
            +
            `Latest update: `
            +
            `${formatDate(trackerData.as_of_date)}. `
            +
            `${trackerData.total_applicants} applicant records currently available.`;


        document.getElementById(
            "calculateButton"
        ).disabled = false;

    }

    catch (error) {

        console.error(error);

        status.textContent =
            "The latest VisaTracker data could not be loaded. "
            +
            "Please try again later.";

    }
}


/* ============================================================
   INITIALISE PAGE
============================================================ */

document.getElementById(
    "calculateButton"
).disabled = true;


document.getElementById(
    "calculateButton"
).addEventListener(
    "click",
    calculate
);


/*
Allow Enter key to calculate.
*/

document.getElementById(
    "joiningDate"
).addEventListener(
    "keydown",
    function (event) {

        if (
            event.key === "Enter"
        ) {

            calculate();
        }
    }
);


loadTrackerData();
