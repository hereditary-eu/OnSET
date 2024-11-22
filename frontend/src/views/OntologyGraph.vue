<script setup lang="ts">
import { ref, watch, reactive, computed, onMounted } from 'vue'
import * as d3 from 'd3'
import { Api, type Subject } from '@/api/client.ts/Api';
import { de, fa, he } from 'vuetify/locale';
import type { UnionType } from 'typescript';
import { type NodeType, type SubjectInGraph, GraphMan } from '@/utils/d3-man/GraphMan';
import { BACKEND_URL } from '@/utils/config';
const graph_data = ref([] as SubjectInGraph[])
const api = new Api({
    baseURL: BACKEND_URL
})

const nodes_comp = ref([] as (NodeType)[])
const links_comp = ref([] as (d3.SimulationLinkDatum<NodeType>)[])

const graph_man = new GraphMan()

function compute_nodelinks(adding = false) {
    console.log('node_links computing')
    const recursive_nodes = (subject: SubjectInGraph) => {
        if (!graph_man.nodes.find(n => n.subject_id == subject.subject_id)) {
            graph_man.nodes.push({ id: subject.subject_id, ...subject })
        }

        for (let desc_type in subject.descendants) {

            subject.descendants[desc_type].forEach(desc => {

                if (!graph_man.links.find(l => l.source == subject.subject_id && l.target == desc.subject_id)) {
                    graph_man.links.push({ source: subject.subject_id as any, target: desc.subject_id as any })
                }
                recursive_nodes(desc)
            })
        }
    }
    graph_data.value.map((c) => {
        recursive_nodes(c)
    })
    console.log('nodes', graph_man.nodes)
    console.log('links', graph_man.links)
    nodes_comp.value = graph_man.nodes
    links_comp.value = graph_man.links
    return { nodes: graph_man.nodes, links: graph_man.links }
}
function applyDescendants(parent: SubjectInGraph, descendants: SubjectInGraph[], descendant_type: string = "subClassOf") {
    let find_subject_in_tree = (subject: SubjectInGraph): SubjectInGraph => {
        if (subject.subject_id == parent.subject_id) {
            return subject
        }
        for (let dt in subject.descendants) {
            for (let desc of subject.descendants[dt]) {
                let found = find_subject_in_tree(desc)
                if (found) {
                    return found
                }
            }
        }
        return null
    }
    console.log('subject', parent)
    let subject: SubjectInGraph = null
    for (let root of graph_data.value) {
        let found = find_subject_in_tree(root)
        if (found) {
            subject = found
            console.log('found', found)
            break
        }
    }
    if (!subject.descendants) {
        subject.descendants = {}
    }
    subject.descendants[descendant_type] = descendants
}
async function loadSubClasses(parent: SubjectInGraph,) {
    const resp = await api.classes.getClassClassesSubclassesGet({
        cls: parent.subject_id
    })//TODO: implement descendant_type
    // console.log('resp', resp)
    let child_subjects = resp.data as SubjectInGraph[]
    applyDescendants(parent, child_subjects, "subClassOf")
}
async function loadNIs(parent: SubjectInGraph) {
    const resp = await api.classes.getNamedIndividualsClassesNamedIndividualsGet({
        cls: parent.subject_id
    })//TODO: implement descendant_type
    // console.log('resp', resp)
    let child_subjects = resp.data as SubjectInGraph[]
    applyDescendants(parent, child_subjects, "NamedIndividual")

}
async function expandGraph(parent: SubjectInGraph) {
    if (parent.expanded) {
        return
    }
    parent.expanded = true
    await loadSubClasses(parent)
    await loadNIs(parent)
    compute_nodelinks(false)
    graph_man.restartGraph()
}
watch(() => { nodes_comp.value; links_comp.value }, () => {
    console.log('node_links changed')
    graph_man.initGraph()
}, { deep: true })
onMounted(() => {
    graph_man.clicked_node = (node: NodeType) => {
        console.log('clicked_node', node)
        expandGraph(node as SubjectInGraph)
    }
    (async () => {
        const resp = await api.classes.getRootClassesClassesRootsGet()
        graph_data.value.push(...resp.data as SubjectInGraph[])

        console.log('graph_data', graph_data)
        compute_nodelinks()
    })().catch(console.error)

    // .style('background-color', 'red')
})

</script>
<template>
    <main>
        <div class="graph_wrapper"></div>

    </main>
</template>
<style scoped>
.graph_wrapper {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 70vh;
    width: 80;
    background-color: #ffffff;
}
</style>