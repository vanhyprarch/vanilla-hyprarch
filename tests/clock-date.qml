pragma ComponentBehavior: Bound

import QtQuick
import QtTest
import "../home/.config/quickshell/vanhyprarch/components/ClockDate.js" as ClockDate

TestCase {
    id: testCase

    name: "ClockDate"
    when: windowShown
    visible: true
    width: 400
    height: 300

    function test_english_date_abbreviations() {
        const examples = [
            { date: new Date(2026, 0, 5), expected: "5 Jan" },
            { date: new Date(2026, 8, 24), expected: "24 Sep" },
            { date: new Date(2026, 11, 31), expected: "31 Dec" }
        ]
        for (const example of examples)
            compare(ClockDate.formatDate(example.date), example.expected)
    }

    function test_all_month_names_are_english_and_capitalized() {
        const expected = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        for (let month = 0; month < expected.length; month++)
            compare(ClockDate.formatDate(new Date(2026, month, 1)),
                "1 " + expected[month])
    }
}
