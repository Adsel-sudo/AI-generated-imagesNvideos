import type { GenerateTaskRequestPayload, OptimizeRequestPayload, UploadedReferenceFile } from "@/src/types/image";
import type { GenerationTarget } from "@/src/types/api";
import type { UploadedReferenceAsset, WorkbenchDraft } from "@/src/types/workbench";

const DEFAULT_TASK_TYPE = "image";

const mapReferenceItems = (items: UploadedReferenceAsset[], role: string): UploadedReferenceFile[] =>
  items.map((item) => ({ file_id: item.file_id, role }));

const mapReferencesToPayload = (draft: WorkbenchDraft): UploadedReferenceFile[] => [
  ...mapReferenceItems(draft.references.product, "product"),
  ...mapReferenceItems(draft.references.composition, "composition"),
  ...mapReferenceItems(draft.references.pose, "pose"),
  ...mapReferenceItems(draft.references.style, "style"),
];

const parseSizeToTarget = (size: string): GenerationTarget => {
  const matched = size.match(/^(\d+)x(\d+)$/i);
  const width = matched ? Number(matched[1]) : undefined;
  const height = matched ? Number(matched[2]) : undefined;

  return {
    target_type: "image",
    width,
    height,
    size,
    n_outputs: 1,
  };
};

const buildUsageOptions = (draft: WorkbenchDraft) => ({
  size: draft.size,
  style_preference: draft.style_preference,
  preserve_product_fidelity: draft.preserve_product_fidelity,
  implicit_prompt_plan: draft.reserved.implicit_prompt_plan,
});

type BuildPayloadParams = {
  draft: WorkbenchDraft;
};

export const buildOptimizePayload = ({ draft }: BuildPayloadParams): OptimizeRequestPayload => ({
  task_type: DEFAULT_TASK_TYPE,
  raw_request: draft.raw_request,
  references: mapReferencesToPayload(draft),
  usage_options: buildUsageOptions(draft),
  generation_targets: [parseSizeToTarget(draft.size)],
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
  references: mapReferencesToPayload(draft),
  generation_targets: [parseSizeToTarget(draft.size)],
  usage_options: buildUsageOptions(draft),
});
