const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

function formatDate(date) {
    return date.getDate() + " " + months[date.getMonth()]
}
