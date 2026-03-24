import type { GenerateTaskRequestPayload, OptimizeRequestPayload, UploadedReferenceFile } from "@/src/types/image";
import type { UploadedReferenceAsset, WorkbenchDraft } from "@/src/types/workbench";

const mapReferenceItems = (items: UploadedReferenceAsset[], role: string): UploadedReferenceFile[] =>
  items.map((item) => ({ file_id: item.file_id, role }));

const mapReferencesToPayload = (draft: WorkbenchDraft): UploadedReferenceFile[] => [
  ...mapReferenceItems(draft.references.product, "product"),
  ...mapReferenceItems(draft.references.composition, "composition"),
  ...mapReferenceItems(draft.references.pose, "pose"),
  ...mapReferenceItems(draft.references.style, "style"),
];

type BuildPayloadParams = {
  draft: WorkbenchDraft;
  session_id: string;
  conversation_id: string;
};

export const buildOptimizePayload = ({
  draft,
  session_id,
  conversation_id,
}: BuildPayloadParams): OptimizeRequestPayload => ({
  request_text: draft.raw_request,
  size: draft.size,
  style: draft.style_preference,
  references: mapReferencesToPayload(draft),
  preserve_product_fidelity: draft.preserve_product_fidelity,
  session_id,
  conversation_id,
  implicit_prompt_plan: draft.reserved.implicit_prompt_plan,
});

export const buildGeneratePayload = ({
  draft,
  session_id,
  conversation_id,
  optimized_prompt_cn,
}: BuildPayloadParams & { optimized_prompt_cn?: string }): GenerateTaskRequestPayload => ({
  request_text: optimized_prompt_cn || draft.raw_request,
  optimized_prompt_cn,
  size: draft.size,
  style: draft.style_preference,
  references: mapReferencesToPayload(draft),
  preserve_product_fidelity: draft.preserve_product_fidelity,
  session_id,
  conversation_id,
  implicit_prompt_plan: draft.reserved.implicit_prompt_plan,
});
