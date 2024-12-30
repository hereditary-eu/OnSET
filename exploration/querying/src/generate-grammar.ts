import * as fs from 'fs/promises';
(async () => {
    const { compile, serializeGrammar } = await import('@intrinsicai/gbnfgen')
    let type_files = await fs.glob('src/**/types-*.ts')
    for await (let file of type_files) {
        let content = await fs.readFile(file, 'utf-8')
        let root_type = content.match(/\/\/ROOT_TYPE: (\w+)/)
        let grammar = await compile(content, root_type[1])
        let serialized = serializeGrammar(grammar)
        await fs.writeFile(file.replace('types-', '../grammars/').replace('.ts', '.gbnf'), serialized)
    }
})().catch(console.error)