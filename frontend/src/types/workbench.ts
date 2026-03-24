export type ReferenceBuckets = {
  product: UploadedReferenceAsset[];
  composition: UploadedReferenceAsset[];
  pose: UploadedReferenceAsset[];
  style: UploadedReferenceAsset[];
};

export type ReferenceCategory = keyof ReferenceBuckets;

export type UploadedReferenceAsset = {
  local_id: string;
  file_id: string;
  file_name?: string;
  mime_type?: string;
  preview_url: string;
};

export type WorkbenchDraft = {
  raw_request: string;
  references: ReferenceBuckets;
  size: string;
  style_preference: string;
  preserve_product_fidelity: boolean;
  reserved: {
    session_id?: string;
    conversation_id?: string;
    implicit_prompt_plan?: string;
  };
};

export const createEmptyWorkbenchDraft = (): WorkbenchDraft => ({
  raw_request: "",
  references: {
    product: [],
    composition: [],
    pose: [],
    style: [],
  },
  size: "1600x1600",
  style_preference: "",
  preserve_product_fidelity: false,
  reserved: {},
});
