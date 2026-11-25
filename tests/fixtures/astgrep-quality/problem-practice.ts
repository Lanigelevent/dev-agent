// problem-practice.ts — TypeScript 实践规则命中
interface EmptyProps { }  // HIT: ts-empty-interface

let badValue: any = 42;  // HIT: ts-no-explicit-any

function badAnyParam(x: any): void {  // also HIT: ts-no-explicit-any (via let pattern on badValue above)
    return;
}
