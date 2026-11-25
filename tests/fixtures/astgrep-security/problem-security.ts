// problem-security.ts — TypeScript 问题样例
function badCast(val: unknown) {
    return val as any;  // HIT: ts-unsafe-any-cast
}
