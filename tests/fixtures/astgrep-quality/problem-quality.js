// problem-quality.js — 9 条代码质量规则全命中
function quality(a, b, obj) {
    try {
        riskyOp();
    } catch (e) { }  // HIT: js-empty-catch

    if (a == b) { return; }  // HIT: js-loose-equality

    throw "error message";  // HIT: js-throw-string

    if (typeof a === "undefined") { return; }  // HIT: js-typeof-undefined

    with (obj) {  // HIT: js-with-statement
        prop = 1;
    }

    void 0;  // HIT: js-void-expr

    delete obj.prop;  // HIT: js-delete-expr

    globalVar = 42;  // 普通隐式全局赋值：js-implicit-global 已因误报率过高下线

    const flag = !!a;  // HIT: js-double-not

    const arr = new Array(10);  // HIT: js-new-array

    return flag;
}
