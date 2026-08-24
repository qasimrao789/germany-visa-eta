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
   CALENDAR DAY HELPERS
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


function maxDate(
    first,
    second
) {

    return first > second
        ? first
        : second;
}


/* ============================================================
   COUNT SUBMISSIONS BETWEEN DATES
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
   ADD BUSINESS DAYS
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
        Sunday = 0
        Saturday = 6
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
   CALCULATE PROCESSING SPEEDS
============================================================ */

function calculateSpeeds() {

    const asOf =
        trackerData.as_of_date;

    const first =
        trackerData.first_submission_date;


    /* --------------------------------------------------------
       LONG-TERM SPEED
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
       RECENT SPEED
    --------------------------------------------------------- */

    const configuredWindow =
        trackerData.recent_window_days
        || 14;

    const proposedRecentStart =
        subtractDays(
            asOf,
            configuredWindow - 1
        );

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
   COUNT WAITING APPLICANTS BEFORE USER
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
   READ USER'S BUFFER
============================================================ */

function getSelectedBuffer() {

    const input =
        document.getElementById(
            "bufferInput"
        );

    let buffer =
        parseInt(
            input.value,
            10
        );


    if (
        Number.isNaN(buffer)
    ) {

        buffer = 50;
    }


    if (
        buffer < 0
    ) {

        buffer = 0;
    }


    if (
        buffer > 500
    ) {

        buffer = 500;
    }


    input.value =
        buffer;


    return buffer;
}


/* ============================================================
   ETA FROM QUEUE SIZE
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


    const estimatedDays =
        Math.ceil(
            queue / speed
        );


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
   RENDER BREAKDOWN
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
                your selected safety buffer
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
       PEOPLE WAITING BEFORE USER
    --------------------------------------------------------- */

    const before =
        countWaitingBefore(
            joiningDate
        );


    /* --------------------------------------------------------
       SAME-DAY WAITING APPLICANTS
    --------------------------------------------------------- */

    const sameDay =
        trackerData
            .waiting_by_join_date[
                joiningDate
            ]
        || 0;


    /* --------------------------------------------------------
       USER-SELECTED BUFFER
    --------------------------------------------------------- */

    const buffer =
        getSelectedBuffer();


    /* ========================================================
       OPTIMISTIC
    ========================================================= */

    const optimisticSameDayAhead =
        0;

    const optimisticQueue =
        before
        +
        optimisticSameDayAhead
        +
        buffer;


    /* ========================================================
       MIDDLE
    ========================================================= */

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


    /* ========================================================
       CONSERVATIVE
    ========================================================= */

    const conservativeSameDayAhead =
        sameDay;

    const conservativeQueue =
        before
        +
        conservativeSameDayAhead
        +
        buffer;


    /* ========================================================
       LONG-TERM ETAS
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
       RECENT ETA
    ========================================================= */

    const recentMiddleETA =
        etaFromQueue(
            middleQueue,
            speeds.recentSpeed
        );


    /* ========================================================
       MAIN RESULT
    ========================================================= */

    document.getElementById(
        "primaryDate"
    ).textContent =
        formatDate(
            middleETA.date
        );


    /* ========================================================
       SPEEDS
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
       QUEUE COUNTS
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
       OPTIMISTIC DISPLAY
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
       MIDDLE DISPLAY
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
       CONSERVATIVE DISPLAY
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
       RECENT ETA DISPLAY
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
   BUFFER PRESET BUTTONS
============================================================ */

function setupBufferPresets() {

    const buttons =
        document.querySelectorAll(
            ".buffer-preset"
        );


    buttons.forEach(
        function (button) {

            button.addEventListener(
                "click",
                function () {

                    const value =
                        button.dataset.buffer;

                    document.getElementById(
                        "bufferInput"
                    ).value =
                        value;


                    buttons.forEach(
                        function (otherButton) {

                            otherButton.classList.remove(
                                "selected"
                            );
                        }
                    );


                    button.classList.add(
                        "selected"
                    );

                }
            );
        }
    );
}


/* ============================================================
   LOAD TRACKER DATA
============================================================ */

async function loadTrackerData() {

    const status =
        document.getElementById(
            "dataStatus"
        );


    try {

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
           MAX DATE
        ----------------------------------------------------- */

        const dateInput =
            document.getElementById(
                "joiningDate"
            );

        dateInput.max =
            trackerData.as_of_date;


        /* ----------------------------------------------------
           DEFAULT BUFFER
        ----------------------------------------------------- */

        const recommendedBuffer =
            trackerData.buffer_people
            || 50;


        document.getElementById(
            "bufferInput"
        ).value =
            recommendedBuffer;


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
        ).disabled =
            false;

    }

    catch (error) {

        console.error(
            error
        );


        status.textContent =
            "The latest VisaTracker data could not be loaded. "
            +
            "Please try again later.";

    }
}


/* ============================================================
   INITIALISE
============================================================ */

document.getElementById(
    "calculateButton"
).disabled =
    true;


document.getElementById(
    "calculateButton"
).addEventListener(
    "click",
    calculate
);


/* Press Enter from date field */

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


/* Press Enter from buffer field */

document.getElementById(
    "bufferInput"
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


setupBufferPresets();

loadTrackerData();
