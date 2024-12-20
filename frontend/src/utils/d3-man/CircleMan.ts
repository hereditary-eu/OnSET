

import * as d3 from 'd3'
import { Api, type Property, type Subject } from '@/api/client.ts/Api';
export class SubjectInCircle implements Subject {
    subject_id: string;
    label: string;
    spos: Record<string, Property> = {};
    subject_type?: string = 'split';
    refcount?: number = 0;
    descendants?: Record<string, Subject[]> = {};
    total_descendants?: number = 0;
    expanded: boolean = false
    children?: SubjectInCircle[]
    n_id: number = 0
}

export class CircleMan {
    nodes: SubjectInCircle[] = []

    node_d3: d3.Selection<any, SubjectInCircle, any, any> = null

    svg_d3: d3.Selection<SVGSVGElement, unknown, HTMLElement, any> = null

    color = d3.scaleLinear()
        .domain([0, 10])
        .range(["hsl(152,80%,80%)", "hsl(228,30%,40%)"] as any)
        .interpolate(d3.interpolateHcl as any);
    color_type = d3.scaleOrdinal(d3.schemePastel2);

    width = 1000
    height = 500
    clicked_node: (NodeType) => void = null

    nodes_g_d3: d3.Selection<any, any, any, any> = null
    root: d3.HierarchyCircularNode<SubjectInCircle> = null
    focus: d3.HierarchyCircularNode<SubjectInCircle> = null
    hierarchy: d3.HierarchyNode<SubjectInCircle> = null
    private node_counter = 0
    constructor() {

    }
    mapNodesToChildren(node: SubjectInCircle): SubjectInCircle {
        let children: SubjectInCircle[] = []
        for (let key in node.descendants) {
            let child = new SubjectInCircle()
            child.subject_id = `${node.subject_id}_${key}`
            child.label = `${key} of ${node.label}`
            child.expanded = true
            if (node.descendants[key].length == 0) {
                child.subject_type = 'leaf'
            } else {
                child.children = node.descendants[key].map(this.mapNodesToChildren.bind(this))
                child.children.forEach(child => child.n_id = this.node_counter++)
                child.total_descendants = child.children.reduce((acc, child) => acc + child.refcount, 0)
                child.n_id = this.node_counter++
                children.push(child)
            }


        }
        node.expanded = true
        return {
            ...node,
            children: children
        }
    }
    restartPackedCircles() {

        const mapped_nodes: SubjectInCircle[] = this.nodes.map(this.mapNodesToChildren.bind(this))
        mapped_nodes.forEach(child => child.n_id = this.node_counter++)

        console.log('restarting graph', this.nodes, mapped_nodes)
        const data: SubjectInCircle = {
            subject_id: 'root',
            expanded: true,
            spos: {},
            label: 'root',
            refcount: 0,
            subject_type: 'root',
            total_descendants: mapped_nodes.reduce((acc, child) => acc + child.total_descendants, 0),
            children: mapped_nodes,
            n_id: this.node_counter++
        }
        this.hierarchy = d3.hierarchy(data, (d) => d.children)
            .sum(d => d.children?.length || 0)
            .sort((a, b) => b.value - a.value)
        this.root = d3.pack<SubjectInCircle>()
            .size([this.width, this.height])
            .radius(d => Math.sqrt(d.data.total_descendants) || 0)

            .padding(d => d.data.children ? 0.5 : 1)(this.hierarchy);
        console.log('root', this.root)
        let max_depth = 0
        this.root.each(d => {
            if (d.depth > max_depth) {
                max_depth = d.depth
            }
        })

        this.color = d3.scaleLinear()
            .domain([0, max_depth])
            .range(["hsl(152,80%,80%)", "hsl(228,30%,40%)"] as any)
            .interpolate(d3.interpolateHcl as any);

        // Create the SVG container.
        const svg = this.svg_d3
        // Append the nodes.
        const node = svg.append("g")
            .selectAll("circle")
            .data(this.root.descendants().slice(1))
            .join("circle")
            .attr("fill", d => d.children ? this.color(d.depth) : d3.color(this.color_type(d.data.subject_type)).brighter(0.5).toString())
            // .attr("pointer-events", d => !d.children ? "none" : null)
            .on("mouseover", function (this, e, d) {
                // console.log('mouseover', e, d)
                d3.select(this).attr("stroke", "#000");
                d3.select(`#label_${d.data.n_id}`)
                    .style("display", "inline")
                    .style("fill-opacity", 1);
            })
            .on("mouseout", (e, d) => {
                d3.select(e.currentTarget).attr("stroke", null);
                d3.select(`#label_${d.data.n_id}`)
                    .style("display", d.parent === this.focus ? "inline" : "none")
                    .style("fill-opacity", d.parent === this.focus ? 1 : 0);

            })
            .on("click", (event, d) => {
                if (!d.children && this.clicked_node) {
                    event.stopPropagation()
                    this.clicked_node(d.data)
                    return
                }
                if (this.focus !== d) zoom(event, d), event.stopPropagation()


            });

        // Append the text labels.
        const label = svg.append("g")
            .style("font", "10px sans-serif")
            .attr("pointer-events", "none")
            .attr("text-anchor", "middle")
            .selectAll("text")
            .data(this.root.descendants())
            .join("text")
            .attr('id', d => `label_${d.data.n_id}`)
            .style("fill-opacity", d => d.parent === this.root ? 1 : 0)
            .style("display", d => d.parent === this.root ? "inline" : "none")
            .text(d => d.data.label);

        // Create the zoom behavior and zoom immediately in to the initial focus node.
        svg.on("click", (event) => zoom(event, this.root));
        this.focus = this.root;
        let view;

        let zoomTo = (v) => {
            const k = this.width / v[2];

            view = v;

            label.attr("transform", d => `translate(${(d.x - v[0]) * k},${(d.y - v[1]) * k})`);
            node.attr("transform", d => `translate(${(d.x - v[0]) * k},${(d.y - v[1]) * k})`);
            node.attr("r", d => d.r * k);
        }
        zoomTo([this.focus.x, this.focus.y, this.focus.r * 2]);

        let zoom = (event, d) => {
            const focus0 = focus;

            this.focus = d;

            const transition = svg.transition()
                .duration(event.altKey ? 7500 : 750)
                .tween("zoom", d => {
                    const i = d3.interpolateZoom(view, [this.focus.x, this.focus.y, this.focus.r * 2]);
                    return t => zoomTo(i(t));
                });
            let selector = (d: d3.HierarchyCircularNode<SubjectInCircle>) => (d.parent === this.focus || (d === this.focus && !d.children));
            label
                .filter(function (d) { return selector(d) || (this as any).style.display === "inline"; })
                .transition(transition)
                .style("fill-opacity", d => selector(d) ? 1 : 0)
                .on("start", function (d) { if (selector(d)) (this as any).style.display = "inline"; })
                .on("end", function (d) { if (!selector(d)) (this as any).style.display = "none"; });
        }

    }
    initPackedCircles() {

        // Create a simulation with several forces.


        // Create the SVG container.
        d3.select('.graph_wrapper').selectAll("*").remove()
        this.svg_d3 = d3.select('.graph_wrapper')
            .append('svg')
            .attr('width', '100%')
            .attr('height', '100%')
            .attr("viewBox", [-this.width, -this.height, this.width * 2, this.height * 2])


        this.nodes_g_d3 = this.svg_d3.append("g")
        this.restartPackedCircles()
        // Reheat the simulation when drag starts, and fix the subject position.


        // When this cell is re-run, stop the previous simulation. (This doesn’t
        // really matter since the target alpha is zero and the simulation will
        // stop naturally, but it’s a good practice.)
        // invalidation.then(() => simulation.stop());
        //TODO!
    }
    addLink(from: string, to: string, count: number) {
        let find_in_descendants = (node: d3.HierarchyNode<SubjectInCircle>, subject_id: string): d3.HierarchyNode<SubjectInCircle> => {
            if (node.data.subject_id === subject_id) {
                return node
            }
            if (!node.children) {
                return null
            }
            for (let child of node.children) {
                let found = find_in_descendants(child, subject_id)
                if (found) {
                    return found
                }
            }
            return null
        }

        let source_node_d3 = find_in_descendants(this.root, from)
        let target_node_d3 = find_in_descendants(this.root, to)

        if (!source_node_d3 || !target_node_d3) {
            console.error('could not find source or target data node')
            return
        }
        console.log('adding link', source_node_d3, target_node_d3)
        const k = this.width / (this.focus.r * 2)
        const path_color = "rgb(128 128 128 / 40%)"
        const link_element = this.svg_d3.append("g")
            .attr("id", `link_${from}_${to}`)
            .attr("class", "link")

        const add_text = (nd: d3.HierarchyNode<SubjectInCircle>) => {
            return link_element
                .append("g")
                .attr("id", `label_${nd.data.n_id}`)
                .attr("transform", `translate(${(nd.x - this.focus.x) * k},${(nd.y - this.focus.y) * k})`)
                .append("text")
                .text(nd.data.label)
                .attr("fill", "black")
                .attr("font-size", "10px")
                .attr("text-anchor", "middle")
                .style("display", "none")
                .style("fill-opacity", 0)
        }
        const source_label = add_text(source_node_d3)
        const target_label = add_text(target_node_d3)

        link_element.append("path")
            .attr("d", `M${(source_node_d3.x - this.focus.x) * k},${(source_node_d3.y - this.focus.y) * k}
                        C 0 0 0 0 ${(target_node_d3.x - this.focus.x) * k},${(target_node_d3.y - this.focus.y) * k}`)

            .attr("stroke-width", Math.log10(count + 1) * 2)
            .style("stroke", path_color)
            .attr("fill", "none")
            .on("mouseover", (e, d) => {
                // console.log('mouseover', e, d)
                d3.select(e.currentTarget).attr("stroke", "rgb(128 128 128 / 80%)")
                source_label.style("display", "inline")
                    .style("fill-opacity", 1)
                target_label.style("display", "inline")
                    .style("fill-opacity", 1)

            })
            .on("mouseout", (e, d) => {
                d3.select(e.currentTarget).attr("stroke", path_color);
                source_label.style("display", "none")
                    .style("fill-opacity", 0)
                target_label.style("display", "none")
                    .style("fill-opacity", 0)
            })


    }
    removeLinks() {
        this.svg_d3.selectAll('.link').remove()
    }
}