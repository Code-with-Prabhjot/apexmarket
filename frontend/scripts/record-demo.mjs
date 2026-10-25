/** Produce the three-minute narrated walkthrough from captured dashboard states. */
import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const out = path.join(root, "output/demo");
const captures = process.env.DEMO_CAPTURE_DIR || path.join(out, "captures");
mkdirSync(path.join(out, "segments"), { recursive: true });
const scenes = [
  ["01-overview.png",20,"Proof before\npayment.","Privacy. Routing. Verification.\nExact settlement.\nOne operational dashboard.","This is ApexMarket Mission Control: one place to route batch inference, inspect verification, and manage exact settlement. This walkthrough uses the explicitly labeled simulation mode. The dashboard also connects to the FastAPI engine through live WebSocket telemetry and server-side API routes. The dark, translucent interface keeps operational decisions in focus."],
  ["02-confidential.png",20,"Privacy is\nthe default.","CONFIDENTIAL starts ON.\nTrusted anchor only.\nSpot providers stay isolated.","Every new session starts with the confidential air-gap switched on. New workloads are classified confidential and stay on the trusted anchor. Spot providers are visibly isolated in the topology. This control sets the sensitivity sent with the actual batch request. A running batch keeps its original classification, so its privacy policy cannot change midway."],
  ["03-batch.png",20,"Launch a\nverified batch.","Up to 5,000 prompts.\nAn explicit spending ceiling.\nOrdered, downloadable results.","Batch submission accepts prompt templates, a prompt count, and a maximum spending budget. The interface validates the request before submission, while the engine enforces its own limits. In this example, we switch to synthetic data and submit fifty prompts. Jobs show their classification, completion progress, and verified cost. Completed results download in original prompt order."],
  ["04-routing.png",20,"See where\nwork goes.","Green: optimal. Amber: slow.\nRed: slashed.\nEdge width follows throughput.","With confidential routing disabled for synthetic work, the topology connects the central router to eligible providers. Curved edges animate while requests are active. Their widths follow reported throughput, or active request counts when throughput is unavailable. Green identifies healthy routing, amber highlights slow responses, and red marks failed or slashed providers. Live telemetry reconnects automatically if the connection drops."],
  ["05-drift.png",25,"Make failure\nvisible.","Inject corrupted mock output.\nInspect verification evidence.\nProtect the payout boundary.","The chaos control injects degraded output into the configured local mock provider. In this simulated walkthrough, the affected node turns red and the verification panel illustrates the rejection and anchor fallback. Live mode reads stored shred attestations rather than inventing successful checks. The five-tier design covers local token billing, rotated canaries, anchor sampling, logprob scoring, and semantic judgment. Failed work earns no payout. Restoring the mock provider is a single action."],
  ["06-cost.png",25,"Compare costs\nwith context.","$0.001361 single-provider cost.\n$0.000923 verified-route cost.\n32.18% difference in source CSV.","The cost chart reads the repository benchmark CSV directly and refreshes periodically. Across the three recorded runs, the single-provider cost is zero point zero zero one three six one dollars, and the verified router cost is zero point zero zero zero nine two three dollars. That is a thirty-two point one eight percent difference. The Batch API bar is explicitly a configurable price scenario unless measured Batch API rows are added. The source CSV does not record whether those runs used live credentials."],
  ["07-makespan.png",15,"Cost and time\nbelong together.","Cost and makespan views.\nEach recorded run selectable.\nScenarios visibly distinct.","Switch to makespan to inspect the time tradeoff. The recorded average is about three point two nine seconds for the baseline and three point nine seconds for the verified route. Individual runs remain selectable. Asynchronous Batch API delivery is distinguished from the recorded synchronous measurements."],
  ["08-ledger.png",18,"Every micro-dollar\nis accounted for.","One dollar = 1,000,000 micros.\nProbation stays in escrow.\nWhole cents pay; fractions carry.","The ledger display preserves six decimal places and shows the underlying integer micro-dollar balance. Probation earnings stay separate from withdrawable funds. Each node's payable amount rounds down to whole cents, while its sub-cent remainder remains in the ledger. This prevents tiny batches from losing value through floating-point rounding or repeated payout fees."],
  ["09-settlement.png",17,"Settle with\nconfidence.","Sandbox settlement.\nDurable reservations and retry IDs.\n50 backend tests passed.","Settle Now submits whole-cent node balances and keeps the remainder. Here, the simulation moves two dollars and ninety-eight cents to pending without moving external money. The sandbox backend uses durable reservations, deterministic batch identifiers, and idempotent reconciliation. Fifty backend tests passed, including payout retries and competing reservations. ApexMarket: route intelligently, verify every shred, and pay only for verified work."],
];
function run(command,args){const r=spawnSync(command,args,{encoding:"utf8"});if(r.status!==0)throw new Error(`${command}: ${r.stderr||r.error||r.status}`);return r.stdout;}
const timestamp=s=>{const n=Math.round(s*1000);return `${String(Math.floor(n/3600000)).padStart(2,"0")}:${String(Math.floor(n/60000)%60).padStart(2,"0")}:${String(Math.floor(n/1000)%60).padStart(2,"0")},${String(n%1000).padStart(3,"0")}`;};
const subtitles=[];let offset=0;
for(const [index,[image,seconds,title,points,speech]] of scenes.entries()){
  const source=path.join(captures,image);if(!existsSync(source))throw new Error(`Capture the dashboard first: ${source}. See frontend/README.md.`);
  const base=path.join(out,"segments",String(index+1).padStart(2,"0"));
  for(const [kind,content]of Object.entries({title,points,speech}))writeFileSync(`${base}-${kind}.txt`,content);
  run("say",["-v","Samantha","-r","175","-f",`${base}-speech.txt`,"-o",`${base}.aiff`]);
  const duration=Number(run("ffprobe",["-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",`${base}.aiff`]).trim());
  if (!Number.isFinite(duration) || duration <= 0) throw new Error("Speech service produced empty audio. Run with local speech-service access.");
  run(process.env.DEMO_PYTHON || "python3", [path.join(root,"frontend/scripts/demo-frame.py"), source, `${base}.png`, title, points, String(index+1)]);
  const filter=`[0:v]null[v];[1:a]atempo=${Math.max(1,duration/(seconds-.7)).toFixed(4)},apad[a]`;
  run("ffmpeg",["-hide_banner","-loglevel","error","-y","-loop","1","-framerate","25","-i",`${base}.png`,"-i",`${base}.aiff`,"-filter_complex",filter,"-map","[v]","-map","[a]","-t",String(seconds),"-c:v","libx264","-preset","veryfast","-crf","21","-pix_fmt","yuv420p","-c:a","aac","-b:a","128k","-ar","44100",`${base}.mp4`]);
  const sentences=speech.match(/[^.!?]+[.!?]/g)||[speech];let elapsed=0;const words=speech.split(/\s+/).length;
  for(const sentence of sentences){const length=sentence.trim().split(/\s+/).length/words*(seconds-.5);subtitles.push(`${subtitles.length+1}\n${timestamp(offset+elapsed)} --> ${timestamp(offset+elapsed+length)}\n${sentence.trim()}\n`);elapsed+=length;}
  offset+=seconds;process.stdout.write(`Scene ${index+1}/9 complete\n`);
}
if(offset!==180)throw new Error("Demo must be exactly three minutes");
writeFileSync(path.join(out,"concat.txt"),scenes.map((_,i)=>`file '${path.join(out,"segments",String(i+1).padStart(2,"0"))}.mp4'`).join("\n"));
run("ffmpeg",["-hide_banner","-loglevel","error","-y","-f","concat","-safe","0","-i",path.join(out,"concat.txt"),"-c:v","copy","-c:a","aac","-t","180","-movflags","+faststart",path.join(out,"apexmarket-mission-control.mp4")]);
writeFileSync(path.join(out,"apexmarket-mission-control.srt"),subtitles.join("\n"));
writeFileSync(path.join(out,"narration.txt"),scenes.map((s,i)=>`${i+1}. ${s[2].replaceAll("\n"," ")}\n${s[4]}`).join("\n\n"));
process.stdout.write(`Saved ${path.join(out,"apexmarket-mission-control.mp4")}\n`);
