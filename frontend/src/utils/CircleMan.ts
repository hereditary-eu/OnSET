

import * as d3 from 'd3'
import { Api, type Subject } from '@/api/client.ts/Api';
export class SubjectInCircle implements Subject {
    subject_id: string;
    label: string;
    spos: Record<string, string[]> = {};
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
        .domain([0, 5])
        .range(["hsl(152,80%,80%)", "hsl(228,30%,40%)"] as any)
        .interpolate(d3.interpolateHcl as any);
    color_type = d3.scaleOrdinal(d3.schemePastel2);

    width = 1000
    height = 500
    clicked_node: (NodeType) => void = null

    nodes_g_d3: d3.Selection<any, any, any, any> = null
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

        // this.node_d3 = this.nodes_g_d3
        //     .selectAll("g")
        //     .data(this.nodes)
        //     .join("g")
        //     .attr('class', 'node_g')
        //     .attr('id', (d) => 'node_g' + d.id)

        // this.node_d3
        //     .append("rect")
        //     .attr('id', (d) => 'node_rect' + d.id)

        // this.node_d3
        //     .append("text")
        //     .attr('stroke-width', '0')
        //     .attr('font-size', d => `${5 + Math.log(d.refcount + 1)}px`)
        //     .attr('font-weight', '0')
        //     .attr('stroke', '#111')
        //     .attr('text-anchor', 'middle')
        //     .attr('alignment-baseline', 'middle')
        //     .attr('cursor', 'grab')
        //     .attr('id', (d) => 'node_text' + d.id)
        //     .text(d => d.label)
        //     .on('click', (evt, d) => {
        //         console.log('clicked', d)
        //         if (this.clicked_node) {
        //             this.clicked_node(d)
        //         }

        //     })
        // const node_h = 15
        // this.node_d3
        //     .selectAll("rect")
        //     .attr("stroke", "#fff")
        //     .attr("stroke-width", 1.5)
        //     .attr('width', (d: any) => (document.getElementById('node_text' + d.id) as unknown as SVGGraphicsElement).getBBox().width + 10)
        //     .attr("height", (d) => node_h)
        //     .attr("x", (d: any) => { return (-(document.getElementById('node_text' + d.id) as unknown as SVGGraphicsElement).getBBox().width) / 2 - 5 })
        //     .attr("y", (d) => -node_h / 2)
        //     .attr("fill", (d: any) => this.color(d.subject_type))
        //     .attr('cursor', 'grab')
        //     .on('click', (evt, d) => {
        //         console.log('clicked', d)
        //         if (this.clicked_node) {
        //             this.clicked_node(d)
        //         }
        //     })

        // this.node_d3.append("title")
        //     .text(d => d.label);


        // Compute the layout
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
        const hierarchy = d3.hierarchy(data, (d) => d.children)
            .sum(d => d.children?.length || 0)
            .sort((a, b) => b.value - a.value)
        const root = d3.pack<SubjectInCircle>()
            .size([this.width, this.height])
            .radius(d => Math.sqrt(d.data.total_descendants) || 0)

            .padding(d => d.data.children ? 0.5 : 1)(hierarchy);
        console.log('root', root)

        // Create the SVG container.
        const svg = this.svg_d3
        // Append the nodes.
        const node = svg.append("g")
            .selectAll("circle")
            .data(root.descendants().slice(1))
            .join("circle")
            .attr("fill", d => d.children ? this.color(d.depth) : d3.color(this.color_type(d.data.subject_type)).brighter(0.5).toString())
            // .attr("pointer-events", d => !d.children ? "none" : null)
            .on("mouseover", function (this, e, d) {
                console.log('mouseover', e, d)
                d3.select(this).attr("stroke", "#000");
                d3.select(`#label_${d.data.n_id}`)
                    .style("display", "inline")
                    .style("fill-opacity", 1);
            })
            .on("mouseout", function (this, e, d) {
                d3.select(this).attr("stroke", null);
                d3.select(`#label_${d.data.n_id}`)
                    .style("display", d.parent === focus ? "inline" : "none")
                    .style("fill-opacity", d.parent === focus ? 1 : 0);

            })
            .on("click", (event, d) => focus !== d && (zoom(event, d), event.stopPropagation()));

        // Append the text labels.
        const label = svg.append("g")
            .style("font", "10px sans-serif")
            .attr("pointer-events", "none")
            .attr("text-anchor", "middle")
            .selectAll("text")
            .data(root.descendants())
            .join("text")
            .attr('id', d => `label_${d.data.n_id}`)
            .style("fill-opacity", d => d.parent === root ? 1 : 0)
            .style("display", d => d.parent === root ? "inline" : "none")
            .text(d => d.data.label);

        // Create the zoom behavior and zoom immediately in to the initial focus node.
        svg.on("click", (event) => zoom(event, root));
        let focus = root;
        let view;

        let zoomTo = (v) => {
            const k = this.width / v[2];

            view = v;

            label.attr("transform", d => `translate(${(d.x - v[0]) * k},${(d.y - v[1]) * k})`);
            node.attr("transform", d => `translate(${(d.x - v[0]) * k},${(d.y - v[1]) * k})`);
            node.attr("r", d => d.r * k);
        }
        zoomTo([focus.x, focus.y, focus.r * 2]);

        let zoom = (event, d) => {
            const focus0 = focus;

            focus = d;

            const transition = svg.transition()
                .duration(event.altKey ? 7500 : 750)
                .tween("zoom", d => {
                    const i = d3.interpolateZoom(view, [focus.x, focus.y, focus.r * 2]);
                    return t => zoomTo(i(t));
                });
            let selector = (d: d3.HierarchyCircularNode<SubjectInCircle>) => (d.parent === focus || (d === focus && !d.children));
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
}