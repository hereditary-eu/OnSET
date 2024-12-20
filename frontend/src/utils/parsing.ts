import { parse, stringify, toJSON, fromJSON } from 'flatted';
class RegisterEntry {
    constructor(public name: string, public cnstr: { new(): {} }) { }
}
let registeredClasses: Record<string, RegisterEntry> = {

}
function reviveRegisteredClasses(key: string, value: any) {
    if (value && value.__parseregister) {
        console.log('Reviving', value)
        let entry = registeredClasses[value.__parseregister]
        if (entry) {
            let obj = new entry.cnstr()
            Object.assign(obj, value)
            return obj
        }
    }
    return value
}

export function stringifyJSON<T>(obj: T): string {
    return stringify(obj);
}
export function parseJSON<T>(json: string): T {
    return parse(json, reviveRegisteredClasses);
}
export function registerClass<C extends { new(): {} }>(constructor: C) {
    constructor.prototype.__parseregister = constructor.name
    registeredClasses[constructor.name] = new RegisterEntry(constructor.name, constructor)
    let anyparam = constructor as { new(...args: any[]): {} }
    return class extends anyparam {
        __parseregister = constructor.name
    } as unknown as C
}