// clean-quality.js — 0 条质量规则命中
'use strict';

function cleanCheck(a, b) {
    try {
        return process(a);
    } catch (e) {
        console.error(e);
        return null;
    }
}

function process(a) {
    if (a === undefined) {
        return null;
    }
    const result = a;
    return result;
}
