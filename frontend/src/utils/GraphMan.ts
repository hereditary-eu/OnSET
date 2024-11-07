

import * as d3 from 'd3'
import { Api, type Subject } from '@/api/client.ts/Api';
export interface SubjectInGraph extends Subject {
    descendants: {
        [key: string]: SubjectInGraph[]
    }
    expanded: boolean
}
export type NodeType = (d3.SimulationNodeDatum & SubjectInGraph & { id: string })
export type LinkType = d3.SimulationLinkDatum<NodeType> & { source: NodeType, target: NodeType }
export class GraphMan {
    nodes: NodeType[] = []
    links: LinkType[] = []
    link_d3: d3.Selection<any, d3.SimulationLinkDatum<NodeType>, any, any> = null
    node_d3: d3.Selection<any, NodeType, any, any> = null

    svg_d3: d3.Selection<SVGSVGElement, unknown, HTMLElement, any> = null

    color = d3.scaleOrdinal(d3.schemeCategory10);

    width = 1000
    height = 500
    simulation: d3.Simulation<NodeType, d3.SimulationLinkDatum<NodeType>> = null
    force_link: d3.ForceLink<NodeType, d3.SimulationLinkDatum<NodeType>> = null
    clicked_node: (NodeType) => void = null

    links_g_d3: d3.Selection<any, any, any, any> = null
    nodes_g_d3: d3.Selection<any, any, any, any> = null

    constructor() {

    }
    restartGraph() {
        this.simulation.stop()
        this.simulation.nodes(this.nodes)
        this.force_link.links(this.links)
        console.log('restarting graph', this.nodes, this.links)
        this.link_d3 = this.links_g_d3
            .selectAll("line")
            .data(this.links)
            .join("line")
            .attr('id', (d) => 'link_id' + d.source)
            .attr("stroke-width", (d: any) => Math.sqrt(d.value));

        this.node_d3 = this.nodes_g_d3
            .selectAll("g")
            .data(this.nodes)
            .join("g")
            .attr('class', 'node_g')
            .attr('id', (d) => 'node_g' + d.id)

        this.node_d3
            .append("rect")
            .attr('id', (d) => 'node_rect' + d.id)

        this.node_d3
            .append("text")
            .attr('stroke-width', '0')
            .attr('font-size', d => `${5 + Math.log(d.refcount + 1)}px`)
            .attr('font-weight', '0')
            .attr('stroke', '#111')
            .attr('text-anchor', 'middle')
            .attr('alignment-baseline', 'middle')
            .attr('cursor', 'grab')
            .attr('id', (d) => 'node_text' + d.id)
            .text(d => d.label)
            .on('click', (evt, d) => {
                console.log('clicked', d)
                if (this.clicked_node) {
                    this.clicked_node(d)
                }

            })
        const node_h = 15
        this.node_d3
            .selectAll("rect")
            .attr("stroke", "#fff")
            .attr("stroke-width", 1.5)
            .attr('width', (d: any) => (document.getElementById('node_text' + d.id) as unknown as SVGGraphicsElement).getBBox().width + 10)
            .attr("height", (d) => node_h)
            .attr("x", (d: any) => { return (-(document.getElementById('node_text' + d.id) as unknown as SVGGraphicsElement).getBBox().width) / 2 - 5 })
            .attr("y", (d) => -node_h/2)
            .attr("fill", (d: any) => this.color(d.subject_type))
            .attr('cursor', 'grab')
            .on('click', (evt, d) => {
                console.log('clicked', d)
                if (this.clicked_node) {
                    this.clicked_node(d)
                }
            })

        this.node_d3.append("title")
            .text(d => d.label);


        let dragstarted = (event) => {
            if (!event.active) this.simulation.alphaTarget(0.3).restart();
            event.subject.fx = event.subject.x;
            event.subject.fy = event.subject.y;
        }

        // Update the subject (dragged node) position during drag.
        let dragged = (event) => {
            event.subject.fx = event.x;
            event.subject.fy = event.y;
        }

        // Restore the target alpha so the simulation cools after dragging ends.
        // Unfix the subject position now that it’s no longer being dragged.
        let dragended = (event) => {
            if (!event.active) this.simulation.alphaTarget(0);
            event.subject.fx = null;
            event.subject.fy = null;
        }
        // Add a drag behavior.
        this.node_d3.call(d3.drag()
            .on("start", dragstarted)
            .on("drag", dragged)
            .on("end", dragended) as any);

        // Set the position attributes of links and nodes each time the simulation ticks.
        this.simulation.on("tick", () => {
            this.link_d3
                .attr("x1", (d: any) => d.source.x)
                .attr("y1", (d: any) => d.source.y)
                .attr("x2", (d: any) => d.target.x)
                .attr("y2", (d: any) => d.target.y);

            this.node_d3
                .attr("transform", d => `translate(${d.x},${d.y})`)
        });

        this.simulation.alphaTarget(0.3).restart()
    }
    initGraph() {

        // Create a simulation with several forces.
        this.force_link = d3.forceLink<NodeType, d3.SimulationLinkDatum<NodeType>>(this.links)
            .id((d) => d.subject_id)
            .distance(100)

        this.simulation = d3.forceSimulation(this.nodes)
            .force("link", this.force_link)
            .force("charge", d3.forceManyBody().strength(-100))
            .force("x", d3.forceX())
            .force("y", d3.forceY());

        // Create the SVG container.
        d3.select('.graph_wrapper').selectAll("*").remove()
        this.svg_d3 = d3.select('.graph_wrapper')
            .append('svg')
            .attr('width', '100%')
            .attr('height', '100%')
            .attr("viewBox", [-this.width / 2, -this.height / 2, this.width, this.height])

        this.links_g_d3 = this.svg_d3.append("g")
            .attr("stroke", "#999")
            .attr("stroke-opacity", 0.6)
        this.nodes_g_d3 = this.svg_d3.append("g")
        this.restartGraph()
        // Reheat the simulation when drag starts, and fix the subject position.


        // When this cell is re-run, stop the previous simulation. (This doesn’t
        // really matter since the target alpha is zero and the simulation will
        // stop naturally, but it’s a good practice.)
        // invalidation.then(() => simulation.stop());
        //TODO!
    }
}