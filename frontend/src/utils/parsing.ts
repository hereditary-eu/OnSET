import { parse, stringify, toJSON, fromJSON } from 'flatted';
class RegisterEntry {
    constructor(public name: string, public cnstr: { new(): {} }) { }
}
let registeredClasses: Record<string, RegisterEntry> = {

}
// Rebuild registered class instances in a parsed object graph, keeping shared references and cycles.
// This runs after flatted has resolved all references: flatted (>= 3.4) resolves nested objects lazily,
// so a reviver that replaces objects would copy them before their children are filled in.
function reviveRegisteredClasses<T>(root: T): T {
    const revived = new Map<any, any>()
    const visit = (value: any): any => {
        if (!value || typeof value !== 'object') {
            return value
        }
        if (revived.has(value)) {
            return revived.get(value)
        }
        if (Array.isArray(value)) {
            revived.set(value, value)
            for (let i = 0; i < value.length; i++) {
                value[i] = visit(value[i])
            }
            return value
        }
        const entry = value.__parseregister ? registeredClasses[value.__parseregister] : undefined
        const target = entry ? new entry.cnstr() as ReconstructableClass : value
        revived.set(value, target)
        for (const key of Object.keys(value)) {
            target[key] = visit(value[key])
        }
        if (entry && typeof target.postConstruct === 'function') {
            target.postConstruct()
        }
        return target
    }
    return visit(root)
}

export function stringifyJSON<T>(obj: T): string {
    return stringify(obj);
}
export function parseJSON<T>(json: string): T {
    return reviveRegisteredClasses(parse(json));
}
export function jsonClone<T>(obj: T): T {
    return parseJSON(stringifyJSON(obj));
}

export class ReconstructableClass {
    constructor() {

    }
    postConstruct() {

    }
}
interface ReconstructableConstructor {
    new(): ReconstructableClass
}
export function registerClass<C extends ReconstructableConstructor>(constructor: C) {
    constructor.prototype.__parseregister = constructor.name
    registeredClasses[constructor.name] = new RegisterEntry(constructor.name, constructor)
    let anyparam = constructor as { new(...args: any[]): {} }
    return class extends anyparam {
        __parseregister = constructor.name
    } as unknown as C
}