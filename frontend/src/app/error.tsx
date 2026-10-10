"use client";
export default function ErrorPage({ reset }: { reset: () => void }) { return <section className="panel" role="alert"><h1>화면을 불러오지 못했습니다</h1><p>잠시 후 다시 시도해 주세요. 입력 중이던 내용은 저장 여부를 확인해 주세요.</p><button onClick={reset}>다시 시도</button></section>; }
