"use client";

import { memo, useEffect, useMemo, useRef } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  Position,
  type NodeProps,
  type Node,
  type Edge,
} from "@xyflow/react";
import { Cpu, ShieldCheck, Zap } from "lucide-react";
import type { Provider, Snapshot } from "@/lib/types";
import { nodeState } from "@/lib/types";
import { demoProviders } from "@/lib/simulation";

type FlowData = {
  title: string;
  subtitle: string;
  hardware?: string;
  pricing?: string;
  roleBadge?: string;
  state: string;
  statusPill?: "Optimal" | "Active" | "Quarantined" | "Air-Gapped";
  liveTokensProcessed?: string;
  metric: string;
  anchor?: boolean;
  router?: boolean;
  locked?: boolean;
};

const ProviderNode = memo(function ProviderNode({ data }: NodeProps<Node<FlowData>>) {
  if (data.router) {
    return (
      <div
        className="flow-card optimal router-card"
        style={{ width: 260, minHeight: 90, padding: "10px 14px" }}
      >
        <Handle type="source" position={Position.Right} />
        <div className="flex items-center justify-between gap-1.5 mb-1.5">
          <div className="flex items-center gap-1.5">
            <span className="node-icon">
              <Zap size={16} />
            </span>
            <span className="dot optimal" />
            <span className="tiny font-bold uppercase tracking-wider text-emerald-400">
              ORCHESTRATOR
            </span>
          </div>
        </div>
        <strong className="text-sm font-bold text-slate-100">{data.title}</strong>
        <span className="flow-sub text-[11px] text-slate-400 block mt-0.5">
          {data.subtitle}
        </span>
        <div className="flow-metric mt-2 pt-1.5 border-t border-emerald-500/30 flex items-center justify-between text-[11px]">
          <span className="text-slate-400">Routing policy</span>
          <b className="font-mono text-emerald-400 font-semibold">{data.metric}</b>
        </div>
      </div>
    );
  }

  const Icon = data.anchor ? ShieldCheck : Cpu;
  const isQuarantined = data.statusPill === "Quarantined" || data.state === "slashed";
  const isActive = data.statusPill === "Active";

  return (
    <div
      className={`flow-card ${data.state} ${data.locked ? "locked" : ""}`}
      style={{ width: 280, minHeight: 92, padding: "10px 14px" }}
    >
      <Handle type="target" position={Position.Left} />

      {/* Top Header: Node icon, status pill, and active role badge */}
      <div className="flex items-center justify-between gap-1.5 mb-1">
        <div className="flex items-center gap-1.5">
          <span className="node-icon">
            <Icon size={15} />
          </span>
          <span className={`dot ${data.state}`} />
          {/* Status Pill: Optimal, Active, Quarantined */}
          {isQuarantined ? (
            <span className="px-1.5 py-0.2 rounded text-[9px] font-bold tracking-wide uppercase bg-red-500/20 text-red-300 border border-red-500/40">
              Quarantined
            </span>
          ) : isActive ? (
            <span className="px-1.5 py-0.2 rounded text-[9px] font-bold tracking-wide uppercase bg-emerald-500/20 text-emerald-300 border border-emerald-500/50 animate-pulse">
              Active
            </span>
          ) : (
            <span className="px-1.5 py-0.2 rounded text-[9px] font-bold tracking-wide uppercase bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
              Optimal
            </span>
          )}
        </div>

        {/* Active Role Badge: AUTHORITATIVE ANCHOR or SPOT WORKER */}
        {data.roleBadge && (
          <span
            className={`px-1.5 py-0.2 rounded text-[9px] font-bold tracking-wider uppercase border ${
              data.anchor
                ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/40"
                : "bg-indigo-500/15 text-indigo-300 border-indigo-500/40"
            }`}
          >
            {data.roleBadge}
          </span>
        )}
      </div>

      {/* Provider Name Title */}
      <strong className="text-xs font-bold text-slate-100 tracking-tight block">
        {data.title}
      </strong>

      {/* Hardware / Model Subtitle & Pricing */}
      <div className="text-[11px] text-slate-300 font-medium mt-0.5 flex items-center justify-between gap-1">
        <span className="truncate">{data.hardware || data.subtitle}</span>
        {data.pricing && (
          <span className="text-[10px] font-mono text-slate-400 shrink-0">
            {data.pricing}
          </span>
        )}
      </div>

      {/* Live tokens processed & Performance Metric */}
      <div className="flow-metric mt-1.5 pt-1 border-t border-slate-700/60 flex items-center justify-between text-[11px]">
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-slate-400">Tokens:</span>
          <b className="text-slate-200 font-mono text-[10px]">
            {data.liveTokensProcessed || "0 tok"}
          </b>
        </div>
        <div className="flex items-center gap-1 text-right">
          <span className="text-[10px] text-slate-400">Perf:</span>
          <b className="text-[#70e4bf] font-mono text-[10px]">{data.metric}</b>
        </div>
      </div>
    </div>
  );
});

const nodeTypes = { provider: ProviderNode };

function TopologyContent({
  providers,
  snapshot,
  isConfidential,
}: {
  providers: Provider[];
  snapshot: Snapshot;
  isConfidential: boolean;
}) {
  const { fitView } = useReactFlow();
  const hasFittedInitialView = useRef(false);
  const prevConfidentialRef = useRef<boolean | null>(null);

  const { nodes, edges } = useMemo(() => {
    const activeProviders = providers.length > 0 ? providers : demoProviders;

    const anchorProvider =
      activeProviders.find(
        (p) =>
          p.trust_tier === "ANCHOR" ||
          p.node_id.includes("nebius") ||
          p.provider_name.includes("Nebius")
      ) ||
      activeProviders[0] ||
      demoProviders[0];

    const spot1Provider =
      activeProviders.find(
        (p) => p.node_id.includes("runpod") || p.provider_name.includes("RunPod")
      ) ||
      activeProviders[1] ||
      demoProviders[1];

    const spot2Provider =
      activeProviders.find(
        (p) => p.node_id.includes("community") || p.provider_name.includes("Community")
      ) ||
      activeProviders[2] ||
      demoProviders[2];

    const anchorLive = snapshot.nodes.find((n) => n.node_id === anchorProvider.node_id);
    const anchorState = nodeState(anchorLive, anchorProvider.is_active);
    const anchorActiveReqs = anchorLive?.active_requests ?? 0;
    const anchorSpeed = anchorLive?.tokens_per_sec ?? anchorProvider.tokens_per_sec;
    const anchorTokens = Math.round(anchorProvider.withdrawable_micros / 0.24);

    const anchorData: FlowData = {
      title: "Nebius Token Factory",
      subtitle: anchorProvider.node_id,
      hardware: "NVIDIA Nemotron-3-Nano (30B)",
      pricing: "$0.06/1M in · $0.24/1M out",
      roleBadge: "AUTHORITATIVE ANCHOR",
      state: anchorState,
      statusPill:
        anchorState === "slashed"
          ? "Quarantined"
          : anchorActiveReqs > 0
          ? "Active"
          : "Optimal",
      liveTokensProcessed: `${
        anchorTokens > 0 ? anchorTokens.toLocaleString() : "7,644,000"
      } tok`,
      anchor: true,
      locked: false,
      metric:
        anchorSpeed !== undefined && anchorSpeed > 0
          ? `${anchorSpeed.toFixed(0)} tok/s`
          : `${anchorActiveReqs} active`,
    };

    const nodesList: Node<FlowData>[] = [];
    const edgesList: Edge[] = [];

    if (isConfidential) {
      // 1. CONFIDENTIAL MODE
      // ApexMarket Orchestrator on left (x: 60, y: 130)
      nodesList.push({
        id: "router",
        type: "provider",
        position: { x: 60, y: 130 },
        data: {
          title: "ApexMarket",
          subtitle: "Capacity-aware inference router",
          state: "optimal",
          metric: "CONFIDENTIAL",
          router: true,
        },
      });

      // Nebius Token Factory Anchor on right (x: 440, y: 130)
      nodesList.push({
        id: anchorProvider.node_id,
        type: "provider",
        position: { x: 440, y: 130 },
        data: anchorData,
      });

      // Active, glowing emerald edge connecting orchestrator to anchor
      edgesList.push({
        id: `route-${anchorProvider.node_id}`,
        source: "router",
        target: anchorProvider.node_id,
        type: "default",
        animated: true,
        style: {
          stroke: "#70e4bf",
          strokeWidth: 2.5,
          opacity: 0.95,
          filter: "drop-shadow(0 0 8px rgba(112, 228, 191, 0.75))",
        },
      });

      // Spot nodes are cleanly hidden and excluded from confidential topology
    } else {
      // 2. NON-CONFIDENTIAL MODE
      // ApexMarket Orchestrator on left (x: 60, y: 130)
      nodesList.push({
        id: "router",
        type: "provider",
        position: { x: 60, y: 130 },
        data: {
          title: "ApexMarket",
          subtitle: "Capacity-aware inference router",
          state: "optimal",
          metric: "SYNTHETIC",
          router: true,
        },
      });

      // Nebius Anchor (x: 440, y: 40)
      nodesList.push({
        id: anchorProvider.node_id,
        type: "provider",
        position: { x: 440, y: 40 },
        data: anchorData,
      });

      edgesList.push({
        id: `route-${anchorProvider.node_id}`,
        source: "router",
        target: anchorProvider.node_id,
        type: "default",
        animated: true,
        style: {
          stroke: anchorState === "slashed" ? "#f87171" : "#70e4bf",
          strokeWidth: 2.5,
          opacity: 0.95,
          filter:
            anchorState === "slashed"
              ? "drop-shadow(0 0 6px rgba(248, 113, 113, 0.6))"
              : "drop-shadow(0 0 8px rgba(112, 228, 191, 0.75))",
        },
      });

      // RunPod Spot (x: 440, y: 150)
      const spot1Live = snapshot.nodes.find((n) => n.node_id === spot1Provider.node_id);
      const spot1State = nodeState(spot1Live, spot1Provider.is_active);
      const spot1ActiveReqs = spot1Live?.active_requests ?? 0;
      const spot1Speed = spot1Live?.tokens_per_sec ?? spot1Provider.tokens_per_sec;
      const spot1Tokens = Math.round(spot1Provider.withdrawable_micros / 0.18);

      nodesList.push({
        id: spot1Provider.node_id,
        type: "provider",
        position: { x: 440, y: 150 },
        data: {
          title: "RunPod Spot Swarm",
          subtitle: spot1Provider.node_id,
          hardware: "NVIDIA H100 SXM5 (Llama-3.1-8B)",
          pricing: "$0.04/1M in · $0.18/1M out",
          roleBadge: "SPOT WORKER",
          state: spot1State,
          statusPill:
            spot1State === "slashed"
              ? "Quarantined"
              : spot1ActiveReqs > 0
              ? "Active"
              : "Optimal",
          liveTokensProcessed: `${
            spot1Tokens > 0 ? spot1Tokens.toLocaleString() : "4,090,277"
          } tok`,
          anchor: false,
          locked: false,
          metric:
            spot1Speed !== undefined && spot1Speed > 0
              ? `${spot1Speed.toFixed(0)} tok/s`
              : `${spot1ActiveReqs} active`,
        },
      });

      edgesList.push({
        id: `route-${spot1Provider.node_id}`,
        source: "router",
        target: spot1Provider.node_id,
        type: "default",
        animated: spot1State !== "slashed",
        style: {
          stroke: spot1State === "slashed" ? "#f87171" : "#818cf8",
          strokeWidth: 2.5,
          opacity: spot1State === "slashed" ? 0.35 : 0.95,
          filter:
            spot1State === "slashed"
              ? "drop-shadow(0 0 6px rgba(248, 113, 113, 0.6))"
              : "drop-shadow(0 0 8px rgba(129, 140, 248, 0.75))",
        },
      });

      // Community Spot (x: 440, y: 260)
      const spot2Live = snapshot.nodes.find((n) => n.node_id === spot2Provider.node_id);
      const spot2State = nodeState(spot2Live, spot2Provider.is_active);
      const spot2ActiveReqs = spot2Live?.active_requests ?? 0;
      const spot2Speed = spot2Live?.tokens_per_sec ?? spot2Provider.tokens_per_sec;
      const spot2Tokens = Math.round(spot2Provider.withdrawable_micros / 0.16);

      nodesList.push({
        id: spot2Provider.node_id,
        type: "provider",
        position: { x: 440, y: 260 },
        data: {
          title: "Community Swarm",
          subtitle: spot2Provider.node_id,
          hardware: "NVIDIA L40S (Llama-3.1-8B)",
          pricing: "$0.035/1M in · $0.16/1M out",
          roleBadge: "SPOT WORKER",
          state: spot2State,
          statusPill:
            spot2State === "slashed"
              ? "Quarantined"
              : spot2ActiveReqs > 0
              ? "Active"
              : "Optimal",
          liveTokensProcessed: `${
            spot2Tokens > 0 ? spot2Tokens.toLocaleString() : "2,667,000"
          } tok`,
          anchor: false,
          locked: false,
          metric:
            spot2Speed !== undefined && spot2Speed > 0
              ? `${spot2Speed.toFixed(0)} tok/s`
              : `${spot2ActiveReqs} active`,
        },
      });

      edgesList.push({
        id: `route-${spot2Provider.node_id}`,
        source: "router",
        target: spot2Provider.node_id,
        type: "default",
        animated: spot2State !== "slashed",
        style: {
          stroke: spot2State === "slashed" ? "#f87171" : "#818cf8",
          strokeWidth: 2.5,
          opacity: spot2State === "slashed" ? 0.35 : 0.95,
          filter:
            spot2State === "slashed"
              ? "drop-shadow(0 0 6px rgba(248, 113, 113, 0.6))"
              : "drop-shadow(0 0 8px rgba(129, 140, 248, 0.75))",
        },
      });
    }

    return { nodes: nodesList, edges: edgesList };
  }, [providers, snapshot, isConfidential]);

  // Fit view once on initial mount and when isConfidential toggles.
  // Nodes are explicitly excluded from dependencies to prevent zoom/pan resets on telemetry updates.
  useEffect(() => {
    if (!hasFittedInitialView.current) {
      const timer = setTimeout(() => {
        fitView({ padding: 0.2 });
        hasFittedInitialView.current = true;
        prevConfidentialRef.current = isConfidential;
      }, 150);
      return () => clearTimeout(timer);
    }

    if (prevConfidentialRef.current !== isConfidential) {
      prevConfidentialRef.current = isConfidential;
      const timer = setTimeout(() => {
        fitView({ padding: 0.2 });
      }, 150);
      return () => clearTimeout(timer);
    }
  }, [isConfidential, fitView]);

  return (
    <div className="relative w-full h-[400px]">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        minZoom={0.2}
        maxZoom={2.0}
        nodesDraggable={true}
        nodesConnectable={false}
        elementsSelectable={false}
        colorMode="dark"
        preventScrolling={false}
      >
        <Background color="#273349" gap={23} size={1} variant={BackgroundVariant.Dots} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

export default function Topology({
  providers,
  snapshot,
  confidential = false,
  isConfidential = confidential,
}: {
  providers: Provider[];
  snapshot: Snapshot;
  confidential?: boolean;
  isConfidential?: boolean;
}) {
  const effectiveConfidential = isConfidential ?? confidential;

  return (
    <div
      className="topology"
      role="img"
      aria-label="ApexMarket router connected to anchor and spot providers"
    >
      <ReactFlowProvider>
        <TopologyContent
          providers={providers}
          snapshot={snapshot}
          isConfidential={effectiveConfidential}
        />
      </ReactFlowProvider>
    </div>
  );
}
