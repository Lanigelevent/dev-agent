// clean-practice.js — 0 条实践规则命中
'use strict';

function processValue(value) {
    const num = Number.parseInt(value, 10);  // safe: Number.parseInt with radix
    return num;
}

function tick() {
    const timer = setTimeout(tick, 1000);  // safe: setTimeout, not setInterval
    return timer;
}

export default function cleanFn() {  // safe: named function, not anonymous
    return processValue('42');
}
