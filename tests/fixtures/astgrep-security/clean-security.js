// clean-security.js — 干净样例：0 安全规则命中
'use strict';

function renderUser(user) {
    const el = document.createElement('div');
    el.textContent = user.name;
    return el;
}

function log(message) {
    const el = document.createElement('p');
    el.textContent = message;
    document.body.appendChild(el);
}

function delayedAlert(msg) {
    setTimeout(() => alert(msg), 1000);
}

function validateInput(input) {
    const re = /^[a-z]+$/;
    return re.test(input);
}

function parseConfig(text) {
    return Object.assign({}, { data: text });
}
