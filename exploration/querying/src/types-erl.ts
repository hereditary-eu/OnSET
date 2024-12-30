//ROOT_TYPE: EntitiesRelations
interface Entity {
    name: string;
    constraints: Constraint[]
}

interface Constraint {
    property: string;
    value: string;
    modifier: string;
}
interface Relations {
    entity: string;
    relation: string;
    target: string;
}
interface EntitiesRelations {
    relations: Relations[];
    entities: Entity[];
}