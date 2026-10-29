import type { Job, SearchResponse } from "@/lib/api";

export type CareerProfile = {
  background: string;
  currentRole: string;
  skills: string;
  experience: string;
  targetRole: string;
  location: string;
  remote: boolean;
  hoursPerWeek: number;
};

export type RoadmapNode = {
  id: string;
  title: string;
  kind: "skill" | "qualification" | "project";
  phase: "requirements" | "practice";
  count: number;
  totalAds: number;
  status: "not-started" | "in-progress" | "completed";
  alreadyKnown: boolean;
  prerequisites: string[];
  evidence: { title: string; url: string }[];
  resource?: { label: string; url: string };
};

export type SavedRoadmap = {
  profile: CareerProfile;
  nodes: RoadmapNode[];
  jobs: { title: string; url: string }[];
  totalCandidates: number;
  analyzedAt: string;
};

const RESOURCE_LINKS: { matches: string[]; label: string; url: string }[] = [
  { matches: ["python"], label: "Python documentation", url: "https://docs.python.org/3/tutorial/" },
  { matches: ["git"], label: "Pro Git book", url: "https://git-scm.com/book/en/v2" },
  { matches: ["sql", "postgres"], label: "PostgreSQL tutorial", url: "https://www.postgresql.org/docs/current/tutorial.html" },
  { matches: ["numpy"], label: "NumPy quickstart", url: "https://numpy.org/doc/stable/user/quickstart.html" },
  { matches: ["pandas"], label: "pandas getting started", url: "https://pandas.pydata.org/docs/getting_started/intro_tutorials/" },
  { matches: ["scikit", "sklearn"], label: "scikit-learn user guide", url: "https://scikit-learn.org/stable/user_guide.html" },
  { matches: ["pytorch", "torch"], label: "PyTorch tutorials", url: "https://pytorch.org/tutorials/" },
  { matches: ["tensorflow"], label: "TensorFlow tutorials", url: "https://www.tensorflow.org/tutorials" },
  { matches: ["docker"], label: "Docker getting started", url: "https://docs.docker.com/get-started/" },
  { matches: ["javascript", "typescript"], label: "TypeScript handbook", url: "https://www.typescriptlang.org/docs/handbook/intro.html" },
  { matches: ["react"], label: "React documentation", url: "https://react.dev/learn" },
  { matches: ["fastapi"], label: "FastAPI tutorial", url: "https://fastapi.tiangolo.com/tutorial/" },
];

function normalized(value: string) {
  return value
    .normalize("NFKC")
    .toLocaleLowerCase()
    .replace(/[يى]/g, "ی")
    .replace(/ك/g, "ک")
    .replace(/[\u200c\u064b-\u065f]/g, " ")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function splitSkills(value: string) {
  return value.split(/[،,;؛\n]+/).map((skill) => skill.trim()).filter(Boolean);
}

function knownSkills(profile: CareerProfile) {
  return splitSkills(profile.skills).map(normalized).filter(Boolean);
}

function isKnown(title: string, skills: string[]) {
  const candidate = normalized(title);
  return skills.some((skill) => candidate === skill || ` ${candidate} `.includes(` ${skill} `) || ` ${skill} `.includes(` ${candidate} `));
}

function resourceFor(title: string) {
  const candidate = normalized(title);
  const resource = RESOURCE_LINKS.find(({ matches }) => matches.some((match) => candidate.includes(match)));
  return resource ? { label: resource.label, url: resource.url } : undefined;
}

function nodeId(kind: "skill" | "qualification", title: string) {
  return `${kind}-${encodeURIComponent(normalized(title))}`;
}

function jobRequirements(job: Job) {
  const requirements: { title: string; kind: "skill" | "qualification" }[] = [];
  for (const skill of Array.isArray(job.skills) ? job.skills : []) {
    if (typeof skill === "string" && skill.trim()) requirements.push({ title: skill.trim(), kind: "skill" });
  }
  for (const software of Array.isArray(job.software) ? job.software : []) {
    if (typeof software?.name === "string" && software.name.trim()) requirements.push({ title: software.name.trim(), kind: "skill" });
  }
  for (const language of Array.isArray(job.languages) ? job.languages : []) {
    if (typeof language?.name === "string" && language.name.trim()) requirements.push({ title: language.name.trim(), kind: "skill" });
  }
  for (const qualification of Array.isArray(job.academic) ? job.academic : []) {
    if (typeof qualification === "string" && qualification.trim()) requirements.push({ title: qualification.trim(), kind: "qualification" });
  }
  return requirements;
}

export function buildRoadmap(
  response: SearchResponse,
  profile: CareerProfile,
  completedIds: string[] = [],
  inProgressIds: string[] = [],
): SavedRoadmap {
  const completed = new Set(completedIds);
  const inProgress = new Set(inProgressIds);
  const profileSkills = knownSkills(profile);
  const ads = new Map<string, { title: string; url: string }>();
  const requirements = new Map<string, { title: string; kind: "skill" | "qualification"; ads: Map<string, { title: string; url: string }> }>();

  for (const result of Array.isArray(response?.results) ? response.results : []) {
    const job = result?.job;
    if (!job || typeof job !== "object") continue;
    const id = String(job.id ?? "").trim();
    if (!id) continue;
    const title = typeof job.title === "string" && job.title.trim() ? job.title : profile.targetRole;
    const url = typeof job.url === "string" ? job.url : "";
    ads.set(id, { title, url });
    for (const requirement of jobRequirements(job)) {
      const key = `${requirement.kind}:${normalized(requirement.title)}`;
      const item = requirements.get(key) ?? { ...requirement, ads: new Map() };
      item.ads.set(id, { title, url });
      requirements.set(key, item);
    }
  }

  const totalAds = ads.size;
  const requirementNodes: RoadmapNode[] = [];
  for (const item of requirements.values()) {
    const id = nodeId(item.kind, item.title);
    const status: RoadmapNode["status"] = completed.has(id)
      ? "completed"
      : inProgress.has(id)
        ? "in-progress"
        : "not-started";
    requirementNodes.push({
      id,
      title: item.title,
      kind: item.kind,
      phase: "requirements",
      count: item.ads.size,
      totalAds,
      status,
      alreadyKnown: item.kind === "skill" && isKnown(item.title, profileSkills),
      prerequisites: [],
      evidence: [...item.ads.values()],
      resource: item.kind === "skill" ? resourceFor(item.title) : undefined,
    });
  }
  requirementNodes.sort((a, b) => b.count - a.count || a.title.localeCompare(b.title));

  const gaps = requirementNodes.filter((node) => !node.alreadyKnown);
  const projectId = "practice-project";
  const projectNode: RoadmapNode = {
    id: projectId,
    title: `${profile.targetRole} — کاربرد عملی مهارت‌ها`,
    kind: "project",
    phase: "practice",
    count: 0,
    totalAds,
    status: completed.has(projectId) ? "completed" : inProgress.has(projectId) ? "in-progress" : "not-started",
    alreadyKnown: false,
    prerequisites: gaps.filter((node) => node.count > 1).map((node) => node.id),
    evidence: [],
  };

  return {
    profile,
    nodes: [...requirementNodes, ...(gaps.length ? [projectNode] : [])],
    jobs: [...ads.values()],
    totalCandidates: Number.isFinite(response.total_candidates) ? response.total_candidates : totalAds,
    analyzedAt: new Date().toISOString(),
  };
}

export function roadmapProgress(nodes: RoadmapNode[]) {
  const trackable = nodes.filter((node) => !node.alreadyKnown);
  const completed = trackable.filter((node) => node.status === "completed").length;
  return { completed, total: trackable.length, percent: trackable.length ? Math.round((completed / trackable.length) * 100) : 0 };
}

export function isBlocked(node: RoadmapNode, nodes: RoadmapNode[]) {
  if (node.status === "completed") return false;
  const byId = new Map(nodes.map((item) => [item.id, item]));
  return node.prerequisites.some((id) => byId.get(id)?.status !== "completed");
}