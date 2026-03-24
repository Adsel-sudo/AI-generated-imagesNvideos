export default function VideoPage() {
  return (
    <main className="min-h-dvh bg-slate-100/80 px-3 py-2 sm:px-4 sm:py-3">
      <div className="mx-auto w-full max-w-[1520px]">
        <section className="rounded-2xl border border-slate-200/80 bg-white/75 p-5 shadow-[0_8px_24px_rgba(30,41,59,0.06)] backdrop-blur">
          <h1 className="text-lg font-semibold tracking-tight text-slate-900">AI视频</h1>
          <div className="mt-1 text-sm text-slate-500">
            当前模型：Veo 3.1 Fast
            {/* 实际模型为 veo-3.1-fast-generate-001 */}
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            视频生成功能后续上线，当前页面仅作为占位。
            <br />
            计划：复用 AI图片 的输入流程与提示词优化能力，输出更适合电商投放的短视频素材。
          </p>

          <div className="mt-4 rounded-xl border border-dashed border-slate-200 bg-slate-100/70 px-4 py-7 text-center">
            <div className="text-sm font-medium text-slate-700">结果展示区域（占位）</div>
            <div className="mt-1 text-xs text-slate-500">后续展示任务状态、生成视频列表与下载</div>
          </div>
        </section>
      </div>
    </main>
  );
}
