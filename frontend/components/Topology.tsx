"use client";
import { memo, useMemo } from "react";
import { ReactFlow, Background, BackgroundVariant, Controls, Handle, Position, type NodeProps, type Node, type Edge } from "@xyflow/react";
import { Cpu, ShieldCheck, Zap } from "lucide-react";
import type { Provider, Snapshot } from "@/lib/types";
import { nodeState } from "@/lib/types";

type FlowData = { title: string; subtitle: string; state: string; metric: string; anchor?: boolean; router?: boolean; locked?: boolean };
const ProviderNode = memo(function ProviderNode({ data }: NodeProps<Node<FlowData>>) {
  const Icon = data.router ? Zap : data.anchor ? ShieldCheck : Cpu;
  return <div className={`flow-card ${data.state} ${data.router ? "router-card" : ""} ${data.locked ? "locked" : ""}`}>
    {!data.router && <Handle type="target" position={Position.Left} />}
    <div className="flow-top"><span className="node-icon"><Icon size={19} /></span><span className={`dot ${data.state}`} /><span className="tiny">{data.router ? "ORCHESTRATOR" : data.anchor ? "TRUSTED ANCHOR" : data.locked ? "AIR-GAPPED" : data.state.toUpperCase()}</span></div>
    <strong>{data.title}</strong><span className="flow-sub">{data.subtitle}</span>
    <div className="flow-metric"><span>{data.router ? "Routing policy" : "Live performance"}</span><b>{data.metric}</b></div>
    {data.router && <Handle type="source" position={Position.Right} />}
  </div>;
});
const nodeTypes = { provider: ProviderNode };
export default function Topology({ providers, snapshot, confidential }: { providers: Provider[]; snapshot: Snapshot; confidential: boolean }) {
  const { nodes, edges } = useMemo(() => {
    const sorted = [...providers].sort((a, b) => Number(b.trust_tier === "ANCHOR") - Number(a.trust_tier === "ANCHOR"));
    const height = Math.max(330, sorted.length * 148);
    const nodes: Node<FlowData>[] = [{ id: "router", type: "provider", position: { x: 25, y: height / 2 - 62 }, data: { title: "ApexMarket", subtitle: "Capacity-aware inference router", state: "optimal", metric: confidential ? "CONFIDENTIAL" : "SYNTHETIC", router: true } }];
    const edges: Edge[] = [];
    sorted.forEach((p, i) => {
      const live = snapshot.nodes.find(n => n.node_id === p.node_id);
      const state = nodeState(live, p.is_active);
      const locked = confidential && p.trust_tier !== "ANCHOR";
      const speed = live?.tokens_per_sec ?? p.tokens_per_sec;
      nodes.push({ id: p.node_id, type: "provider", position: { x: 415, y: i * 148 }, data: { title: p.provider_name, subtitle: p.node_id, state, anchor: p.trust_tier === "ANCHOR", locked, metric: locked ? "Isolated" : speed !== undefined ? `${speed.toFixed(0)} tok/s` : `${live?.active_requests ?? 0} active` } });
      edges.push({ id: `route-${p.node_id}`, source: "router", target: p.node_id, type: "default", animated: !locked && state !== "offline" && (live?.active_requests ?? 0) > 0,
        style: { stroke: locked ? "#1b2533" : state === "slashed" ? "#f87171" : state === "slow" ? "#f2ba65" : "#65ddba", strokeWidth: locked ? 1 : Math.min(7, 1.5 + (speed !== undefined ? speed / 100 : (live?.active_requests ?? 0) / 3)), opacity: locked ? 0.2 : 0.85 } });
    });
    return { nodes, edges };
  }, [providers, snapshot, confidential]);
  return <div className="topology" role="img" aria-label="ApexMarket router connected to anchor and spot providers">
    {!providers.length && <div className="topology-empty">Connect registered providers to see the network.</div>}
    <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.16 }} minZoom={0.25} maxZoom={1.3} nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} colorMode="dark" preventScrolling={false}>
      <Background color="#273349" gap={23} size={1} variant={BackgroundVariant.Dots} /><Controls showInteractive={false} />
    </ReactFlow>
  </div>;
}
