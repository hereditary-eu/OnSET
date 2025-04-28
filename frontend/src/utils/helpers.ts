export function debounce<F extends (...args: []) => void, T>(func: F, wait: number, immediate: Boolean = false): F {
    //https://stackoverflow.com/questions/24004791/what-is-the-debounce-function-in-javascript
    var timeout;
    return function (this: T extends object ? T : unknown) {
        var context = this as unknown, args = arguments;
        var later = function () {
            timeout = null;
            if (!immediate) func.apply(context, args);
        };
        var callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        if (callNow) func.apply(context, args);
    } as F;
}
export function getMax(arr) {
    let len = arr.length;
    let max = -Infinity;

    while (len--) {
        max = arr[len] > max ? arr[len] : max;
    }
    return max;
}
export function getMin(arr) {
    let len = arr.length;
    let min = Infinity;

    while (len--) {
        min = arr[len] < min ? arr[len] : min;
    }
    return min;
}