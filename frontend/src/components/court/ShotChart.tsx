"use client";

import { useEffect, useRef } from "react";
import * as d3 from "d3";

interface Shot {
  court_x: number; // 0-1 normalized
  court_y: number; // 0-1 normalized
  made: boolean;
  event_type: string;
}

interface ShotChartProps {
  shots: Shot[];
  width?: number;
  height?: number;
}

export default function ShotChart({
  shots,
  width = 564,
  height = 300,
}: ShotChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    // Court background
    svg
      .append("rect")
      .attr("width", width)
      .attr("height", height)
      .attr("fill", "#C8A165")
      .attr("rx", 4);

    // Court lines (half court)
    const g = svg.append("g");

    // Outer boundary
    g.append("rect")
      .attr("x", 10)
      .attr("y", 10)
      .attr("width", width - 20)
      .attr("height", height - 20)
      .attr("fill", "none")
      .attr("stroke", "white")
      .attr("stroke-width", 2);

    // Paint / key
    g.append("rect")
      .attr("x", 10)
      .attr("y", height / 2 - 60)
      .attr("width", 114)
      .attr("height", 120)
      .attr("fill", "none")
      .attr("stroke", "white")
      .attr("stroke-width", 2);

    // Three point arc (simplified)
    const arc = d3
      .arc()
      .innerRadius(140)
      .outerRadius(140)
      .startAngle(-Math.PI / 2.5)
      .endAngle(Math.PI / 2.5);

    g.append("path")
      .attr("d", arc as any)
      .attr("transform", `translate(10, ${height / 2})`)
      .attr("fill", "none")
      .attr("stroke", "white")
      .attr("stroke-width", 2);

    // Basket
    g.append("circle")
      .attr("cx", 43)
      .attr("cy", height / 2)
      .attr("r", 6)
      .attr("fill", "none")
      .attr("stroke", "white")
      .attr("stroke-width", 2);

    // Plot shots
    const xScale = d3.scaleLinear().domain([0, 1]).range([10, width - 10]);
    const yScale = d3.scaleLinear().domain([0, 1]).range([10, height - 10]);

    svg
      .selectAll(".shot")
      .data(shots)
      .enter()
      .append("circle")
      .attr("class", "shot")
      .attr("cx", (d) => xScale(d.court_x))
      .attr("cy", (d) => yScale(d.court_y))
      .attr("r", 5)
      .attr("fill", (d) => (d.made ? "#22c55e" : "#ef4444"))
      .attr("opacity", 0.8)
      .attr("stroke", "white")
      .attr("stroke-width", 1);
  }, [shots, width, height]);

  return <svg ref={svgRef} width={width} height={height} />;
}
