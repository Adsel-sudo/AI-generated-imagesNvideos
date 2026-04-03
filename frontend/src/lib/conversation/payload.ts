import type {
  GenerateTaskRequestPayload,
  OptimizeRequestPayload,
  UploadedReferenceFile,
  UsageOptions,
} from "@/src/types/image";
import type { GenerationTarget } from "@/src/types/api";
import type { UploadedReferenceAsset, WorkbenchDraft } from "@/src/types/workbench";

const DEFAULT_TASK_TYPE = "image";
const DEFAULT_N_OUTPUTS = 2;

const mapReferenceItems = (items: UploadedReferenceAsset[], role: string): UploadedReferenceFile[] =>
  items
    .filter((item) => Boolean(item.file_path))
    .map((item) => ({ file_path: item.file_path, role }));

const mapReferencesToPayload = (draft: WorkbenchDraft): UploadedReferenceFile[] => [
  ...mapReferenceItems(draft.references.product, "product"),
  ...mapReferenceItems(draft.references.composition, "composition"),
  ...mapReferenceItems(draft.references.pose, "pose"),
  ...mapReferenceItems(draft.references.style, "style"),
];

const ASPECT_RATIO_PATTERN = /^\s*([1-9]\d*)\s*[:xX/]\s*([1-9]\d*)\s*$/;

export const resolveDraftSize = (draft: WorkbenchDraft): string => {
  if (draft.sizeMode === "custom") {
    const matched = draft.customAspectRatio.match(ASPECT_RATIO_PATTERN);
    if (matched) {
      return `${matched[1]}:${matched[2]}`;
    }
    return "";
  }
  return draft.presetSize;
};

const parseSizeToTarget = (size: string): GenerationTarget => {
  const matched = size.match(ASPECT_RATIO_PATTERN);
  const aspect_ratio = matched ? `${matched[1]}:${matched[2]}` : undefined;

  return {
    target_type: "image",
    aspect_ratio,
    size,
    n_outputs: DEFAULT_N_OUTPUTS,
  };
};

const buildUsageOptions = (draft: WorkbenchDraft): UsageOptions => ({
  size: resolveDraftSize(draft),
  style_preference: draft.style_preference,
  preserve_product_fidelity: draft.preserve_product_fidelity,
  implicit_prompt_plan: draft.reserved.implicit_prompt_plan,
  resolution: draft.resolution,
});

type BuildPayloadParams = {
  draft: WorkbenchDraft;
};

export const buildOptimizePayload = ({ draft }: BuildPayloadParams): OptimizeRequestPayload => ({
  task_type: DEFAULT_TASK_TYPE,
  raw_request: draft.raw_request,
  references: mapReferencesToPayload(draft),
  usage_options: buildUsageOptions(draft),
  generation_targets: [parseSizeToTarget(resolveDraftSize(draft))],
});

export const buildGeneratePayload = ({
  draft,
  optimized_prompt_cn,
  generation_prompt,
  structured_summary,
}: BuildPayloadParams & {
  optimized_prompt_cn: string;
  generation_prompt: string;
  structured_summary: Record<string, unknown>;
}): GenerateTaskRequestPayload => ({
  task_type: DEFAULT_TASK_TYPE,
  optimized_prompt_cn,
  generation_prompt,
  structured_summary,
  resolution: draft.resolution,
  n_outputs: DEFAULT_N_OUTPUTS,
  references: mapReferencesToPayload(draft),
  generation_targets: [parseSizeToTarget(resolveDraftSize(draft))],
  usage_options: buildUsageOptions(draft),
});
