import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type ReaderHost, type ReadingWindow } from "@focus/reader-contracts";
import { FocusReader } from "./FocusReader";
import { discussionFoldKey } from "./discussion-fold";
const chunk = { sourceId: "demo", planId: "p", chunkId: "c", index: 1, total: 2, sectionPath: ["Passage"], sourceLines: [1, 2] as const, sourceMarkdown: "Full original passage", presentationStatus: "source-ready" as const, translation: null, images: [], relevantGlossary: [] };
const base: ReadingWindow = { status: "reading", sessionId: "s", source: { sourceId: "demo", title: "Demo", topicId: null }, current: chunk, history: [],
 conversation: [{chunkId:"c",messageId:"u",role:"user",content:"Question"},{chunkId:"c",messageId:"a",role:"assistant",content:"Answer"},{chunkId:"c",messageId:"b",role:"assistant",content:"Repeated answer"}],
 timeline: [{kind:"reading",eventId:"r1",chunk},{kind:"message",messageId:"u"},{kind:"message",messageId:"a"},{kind:"reading",eventId:"r2",chunk},{kind:"message",messageId:"b"}] };
beforeEach(() => { HTMLDialogElement.prototype.close=vi.fn(); HTMLDialogElement.prototype.showModal=vi.fn(); localStorage.clear(); sessionStorage.clear(); HTMLElement.prototype.scrollTo=vi.fn(); HTMLElement.prototype.scrollIntoView=vi.fn(); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
function setup(view=base) {
 let publish: ((v: ReturnType<typeof readerSuccess<ReadingWindow>>) => void) | undefined;
 const host: ReaderHost = {getReadingWindow: async()=>readerSuccess(view),continueReading:vi.fn(),sendMessage:vi.fn(async()=>readerSuccess(view)),subscribe:fn=>{publish=fn;return()=>{};}};
 const mounted=render(<FocusReader host={host} appearance="mist"/>);
 return {...mounted,host,update:(next:ReadingWindow)=>act(()=>publish?.(readerSuccess(next)))};
}
it("isolates repeated passages, retains source, hides all conversation and persists on remount",async()=>{
 const app=setup(); const buttons=await screen.findAllByRole("button",{name:"收起讨论"});
 fireEvent.click(buttons[0]); expect(screen.getByText("Answer")).not.toBeVisible(); expect(screen.getByText("Question")).not.toBeVisible();
 expect(screen.getByText("Repeated answer")).toBeVisible(); expect(screen.getAllByText("Full original passage")[0]).toBeVisible();
 expect(buttons[0]).toHaveAttribute("aria-expanded","false"); expect(buttons[0]).toHaveFocus();
 app.unmount(); const again=setup(); await screen.findByRole("button",{name:"展开讨论"});
 again.update({...base,sessionId:"other"}); expect(screen.getAllByRole("button",{name:"收起讨论"})).toHaveLength(2);
 again.update({...base,workspace:{workspaceId:"other",instanceId:"i",path:"/fixture"}}); expect(screen.getAllByRole("button",{name:"收起讨论"})).toHaveLength(2);
});
it("keeps streamed updates collapsed and reopens the receiving group on send",async()=>{
 const app=setup(); const buttons=await screen.findAllByRole("button",{name:"收起讨论"}); fireEvent.click(buttons[1]);
 app.update({...base,conversation:base.conversation.map(m=>m.messageId==="b"?{...m,content:"Incremental answer"}:m)});
 expect(screen.getByText("Incremental answer")).not.toBeVisible();
 fireEvent.change(screen.getByRole("textbox"),{target:{value:"New question"}});fireEvent.click(screen.getByRole("button",{name:"发送"}));
 expect(screen.getAllByRole("button",{name:"收起讨论"})).toHaveLength(2);
});
it("falls back to memory with unavailable storage; ignores old/malformed keys",async()=>{
 localStorage.setItem("focus.discussionFold","c");localStorage.setItem(discussionFoldKey("default","demo","s","","r1"),"{broken");
 vi.spyOn(Storage.prototype,"setItem").mockImplementation(()=>{throw Error("quota");});
 setup();const buttons=await screen.findAllByRole("button",{name:"收起讨论"});fireEvent.click(buttons[0]);expect(screen.getByText("Answer")).not.toBeVisible();
 fireEvent.click(screen.getByRole("button",{name:"展开讨论"}));expect(screen.getByText("Answer")).toBeVisible();
});
it("shows no divider for a passage without conversation",async()=>{
 setup({...base,conversation:[],timeline:[{kind:"reading",eventId:"r1",chunk}]});await screen.findByText("Full original passage");expect(screen.queryByRole("button",{name:"收起讨论"})).not.toBeInTheDocument();
});
