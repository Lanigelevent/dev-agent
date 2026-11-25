// problem-security.js — 问题样例：6 条安全规则全命中
'use strict';

function badRender(user) {
    const el = document.getElementById('user');
    el.innerHTML = user.input;  // HIT: js-innerhtml-assignment
}

function badLog(msg) {
    document.write(msg);  // HIT: js-document-write
}

function badTimeout(code) {
    setTimeout("alert('" + code + "')", 1000);  // HIT: js-settimeout-string-arg (concat)
    setTimeout("alert(1)", 1000);  // HIT: js-settimeout-string-arg (literal)
}

function badRegex(pattern) {
    const re = new RegExp(pattern, 'i');  // HIT: js-regex-injection-new
    return re.test(input);
}

function badParse(text) {
    const obj = JSON.parse(text);  // HIT: js-prototype-pollution
    return obj;
}
