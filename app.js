let trackerData = null;

const MS_PER_DAY =
    24 * 60 * 60 * 1000;


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


function calculateSpeeds() {

    const asOf =
        trackerData.as_of_date;

    const first =
        trackerData.first_submission_date;


    // --------------------------------
    // LONG-TERM SPEED
    // --------------------------------

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


    // --------------------------------
    // RECENT SPEED
    // --------------------------------

    const windowDays =
        trackerData.recent_window_days
        || 14;

    const proposedRecentStart =
        subtractDays(
            asOf,
            windowDays - 1
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

        if (day < joiningDate) {
            total += count;
        }
    }

    return total;
}


function etaFromQueue(
    queue,
    speed
) {

    if (!speed || speed <= 0) {
        return null;
    }

    const days =
        Math.ceil(
            queue / speed
        );

    return {
        businessDays: days,

        date:
            addBusinessDays(
                trackerData.as_of_date,
                days
            ),
    };
}


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

    if (!joiningDate) {

        error.textContent =
            "Please select your waiting-list joining date.";

        return;
    }

    if (
        joiningDate
        >
        trackerData.as_of_date
    ) {

        error.textContent =
            "Joining date cannot be in the future.";

        return;
    }


    const speeds =
        calculateSpeeds();


    const before =
        countWaitingBefore(
            joiningDate
        );


    const sameDay =
        trackerData
            .waiting_by_join_date[
                joiningDate
            ]
        || 0;


    const buffer =
        trackerData.buffer_people
        || 50;


    const optimisticAhead =
        before;


    const middleAhead =
        before
        +
        Math.floor(
            sameDay / 2
        );


    const conservativeAhead =
        before
        +
        sameDay;


    const optimisticQueue =
        optimisticAhead
        +
        buffer;


    const middleQueue =
        middleAhead
        +
        buffer;


    const conservativeQueue =
        conservativeAhead
        +
        buffer;


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


    const recentMiddleETA =
        etaFromQueue(
            middleQueue,
            speeds.recentSpeed
        );


    document.getElementById(
        "primaryDate"
    ).textContent =
        formatDate(
            middleETA.date
        );


    document.getElementById(
        "longSpeed"
    ).textContent =
        `${speeds.longSpeed.toFixed(2)}/day`;


    document.getElementById(
        "recentSpeed"
    ).textContent =
        `${speeds.recentSpeed.toFixed(2)}/day`;


    document.getElementById(
        "peopleBefore"
    ).textContent =
        before;


    document.getElementById(
        "sameDay"
    ).textContent =
        sameDay;


    document.getElementById(
        "optimisticDate"
    ).textContent =
        formatDate(
            optimisticETA.date
        );


    document.getElementById(
        "optimisticQueue"
    ).textContent =
        `${optimisticQueue} people used for estimate`;


    document.getElementById(
        "middleDate"
    ).textContent =
        formatDate(
            middleETA.date
        );


    document.getElementById(
        "middleQueue"
    ).textContent =
        `${middleQueue} people used for estimate`;


    document.getElementById(
        "conservativeDate"
    ).textContent =
        formatDate(
            conservativeETA.date
        );


    document.getElementById(
        "conservativeQueue"
    ).textContent =
        `${conservativeQueue} people used for estimate`;


    document.getElementById(
        "recentExpectedDate"
    ).textContent =
        recentMiddleETA
            ? formatDate(
                recentMiddleETA.date
            )
            : "No recent clearances";


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
        `+${buffer}`;


    document.getElementById(
        "lastUpdated"
    ).textContent =
        formatDate(
            trackerData.as_of_date
        );


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


        const input =
            document.getElementById(
                "joiningDate"
            );


        input.max =
            trackerData.as_of_date;


        status.textContent =
            `Live community statistics loaded. `
            +
            `Data updated `
            +
            `${formatDate(trackerData.as_of_date)}.`;


        document.getElementById(
            "calculateButton"
        ).disabled = false;

    }

    catch (error) {

        console.error(error);

        status.textContent =
            "Could not load tracker data. "
            +
            "Please try again later.";

    }
}


document.getElementById(
    "calculateButton"
).disabled = true;


document.getElementById(
    "calculateButton"
).addEventListener(
    "click",
    calculate
);


loadTrackerData();
