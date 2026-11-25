// problem-practice.js — 6 条 JS 实践规则全命中
const config = new Object();  // HIT: js-new-object
const num = parseInt("42");  // HIT: js-parseint-no-radix
const timer = setInterval(function() { return 1; }, 1000);  // HIT: js-setinterval-no-clear

export default function() {  // HIT: js-default-export-anonymous
    return 1;
}

loop: for (let i = 0; i < 10; i++) {  // HIT: js-label-statement
    break loop;
}

throw "bad error";  // HIT: js-throw-new-error
