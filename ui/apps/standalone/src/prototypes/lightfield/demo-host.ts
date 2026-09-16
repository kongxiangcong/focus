// RETAINED THEME PROTOTYPE. Synthetic, memory-only data behind the existing ReaderHost seam.
// Nothing in this module reads Workspace, calls a model, or persists a conversation.
import {
  readerFailure, readerSuccess,
  type ContinueReadingInput, type ReaderChunk, type ReaderHost,
  type ReaderMessage, type ReadingWindow, type SendReaderMessageInput,
} from "@focus/reader-contracts";

const sourceId = "quiet-systems-prototype-article";
const chapters = [
  {
    title: "注意力，是一种选择",
    source: "阅读界面需要保留上下文，但历史内容不能与当前段落争夺注意力。当前段落应当拥有完整对比度，刚刚读过的内容则作为仍可回看的尾迹留在上方。",
    explanation: "好的阅读体验，始于把注意力还给眼前这一件事。\n\n你不需要同时看清整篇文章。让正在读的内容清晰，让读过的内容退到背景，阅读就有了自然的前景与远景。上下文仍然在，只是不再要求你分心。",
    idea: "保留上下文，不等于让所有内容同样醒目。",
  },
  {
    title: "让界面，退后一步",
    source: "当目录、工具栏与正文以相同的视觉强度出现时，读者必须持续决定下一眼看向哪里。界面可以通过减少同时显著的元素，降低这种重复选择的成本。",
    explanation: "每一个抢眼的按钮，都在轻轻打断你的思路。\n\n把不常用的工具藏在触手可及的地方，让导航保持安静。不是减少能力，而是减少此刻需要做的选择。一个安静的系统，会把最清楚的位置留给内容。",
    idea: "能力可以丰富，眼前的选择应该简单。",
  },
  {
    title: "上下文，不必重新寻找",
    source: "在连续的阅读过程中，上一段的结论构成下一段的起点。保留可以回看的空间关系，有助于读者在短暂离开后重新找到自己的思路。",
    explanation: "读过的内容，可以像脚印一样留在身后。\n\n上一段没有消失，它只是变轻了。当你需要回想一个定义、一条因果关系，向上滚动就能找到它。空间上的连续，让思考也不必一次次重新开始。",
    idea: "历史是随时可以回看的线索。",
  },
  {
    title: "一次，只理解一件事",
    source: "Reading Chunk 应围绕一个主要理解任务组织。若一段原文包含需要分别建立的概念或因果链，应在新的理解任务开始前拆分，而不是仅按长度切块。",
    explanation: "深入阅读，并不是一次装下更多内容，\n而是给一个想法，足够展开的空间。\n\n在 FOCUS 中，一个 Chunk 围绕一个主要理解任务。先弄清「问题是什么」，再进入「方法为什么有效」。当思路发生转弯时，界面也陪你轻轻停一下。",
    idea: "以理解任务为边界，而不是以字数为边界。",
  },
  {
    title: "让思考，自然地接续",
    source: "当 Reading Cursor 推进时，上一段仍应保持空间上的连续，新段落再成为语义焦点。读者看到的是一次接力，而不是原文突然被另一块内容替换。",
    explanation: "「继续」应该像翻过一页，而不是走进另一个房间。\n\n上一段缓缓向上，新的讲解来到眼前。光也跟着移动，为注意力指出落点。你能感到思路在前进，却不必重新寻找从哪里开始。",
    idea: "让内容交接，把思路留在原地。",
  },
  {
    title: "好的问题，值得停留",
    source: "追问、解释与讨论不移动 Reading Cursor。只有读者明确请求 Continue Reading，才向后推进一个 Chunk。阅读不以回答正确或理解评价为前提。",
    explanation: "遇到不明白的地方，不需要假装已经读懂。\n\n你可以要一个例子，追问背后的原因，或者用自己的话重新表述。对话会围绕这一段继续展开。什么时候向前走，由你决定。",
    idea: "追问不推进，理解没有倒计时。",
  },
  {
    title: "留下想法，而非所有对话",
    source: "Reading Note 是脱离原始对话仍可理解的有限句子总结或关键词。它保留有价值的想法和来源锚点，而不复制宿主的完整聊天记录。",
    explanation: "值得留下的，往往只是让你停顿的那一句。\n\n阅读笔记不必复刻整场对话。记录一个新想法、一个尚未解决的问题，再留下一条回到原文的线索。下一次回来，你仍能接上今天的思考。",
    idea: "把对话沉淀成少量、可追溯的想法。",
  },
  {
    title: "把阅读的节奏，还给你",
    source: "FOCUS 保存可以跨会话恢复的阅读位置与精简阅读资产，不评价读者的理解、掌握或能力。进度只表示阅读位置，不代表理解程度。",
    explanation: "读到最后，不代表每个问题都有了答案。\n\n这条轨迹记录你走到了哪里，不衡量你理解了多少。你可以回看、停留，带着问题离开，再从同一个地方回来。阅读的节奏，始终属于你。",
    idea: "进度是位置，不是成绩。",
  },
];

export const demoChapters = chapters;
export const demoChunks: ReaderChunk[] = chapters.map((chapter, index) => ({
  sourceId, planId: "plan-prototype", chunkId: `chunk-${String(index + 1).padStart(3, "0")}`,
  index: index + 1, total: chapters.length, sectionPath: ["安静系统", chapter.title],
  sourceLines: [index * 10 + 1, index * 10 + 9], sourceMarkdown: chapter.source,
  translation: null, images: [], relevantGlossary: [], presentationStatus: "presented",
}));

export class LightfieldDemoHost implements ReaderHost {
  private position = 3;
  private sequence = 0;
  private messages: ReaderMessage[] = demoChunks.slice(0, 4).map((chunk, i) => ({
    messageId: `reading-${i}`, chunkId: chunk.chunkId, role: "assistant", content: chapters[i].explanation,
  }));

  constructor() {
    this.messages.push(
      { messageId: "seed-question", chunkId: "chunk-004", role: "user", content: "「一个理解任务」，可以举个例子吗？" },
      { messageId: "seed-answer", chunkId: "chunk-004", role: "assistant", content: "比如读一篇论文：先理解它想解决什么问题，再理解方法怎样解决它。这是两个理解任务，值得分成两个 Chunk，慢慢展开。" },
    );
  }

  private snapshot(): ReadingWindow {
    return {
      status: this.position >= demoChunks.length ? "completed" : "reading",
      source: { sourceId, title: "安静系统：为持续注意力而设计", topicId: null },
      current: demoChunks[this.position] ?? null,
      history: demoChunks.slice(0, this.position), conversation: [...this.messages],
    };
  }

  async getReadingWindow() { return readerSuccess(this.snapshot()); }

  async continueReading(input: ContinueReadingInput) {
    if (demoChunks[this.position]?.chunkId !== input.receipt.chunkId) {
      return readerFailure("cursor-changed", "阅读位置已变化，请重新加载原型。");
    }
    this.position += 1;
    const chunk = demoChunks[this.position];
    if (chunk) this.messages.push({
      messageId: `reading-${this.position}`, chunkId: chunk.chunkId,
      role: "assistant", content: chapters[this.position].explanation,
    });
    return readerSuccess(this.snapshot());
  }

  async sendMessage(input: SendReaderMessageInput) {
    if (!input.receipt) return readerFailure("invalid-request", "Select a chunk first.");
    if (demoChunks[this.position]?.chunkId !== input.receipt.chunkId) {
      return readerFailure("cursor-changed", "请回到当前阅读位置再追问。");
    }
    const question = input.content.trim();
    if (!question) return readerFailure("invalid-request", "先写下你的问题。");
    const chapter = chapters[this.position];
    const answer = question.includes("例子")
      ? `可以把「${chapter.title}」放到读论文的场景里：读完问题定义，先停下来问“为什么这是个问题？”，再继续读方法。你每次只处理眼前这一个理解任务。`
      : question.includes("核心") || question.includes("一句")
        ? `这一段的核心是：${chapter.idea} 你可以继续围绕这个想法追问，阅读位置不会变化。`
        : question.includes("联系")
          ? `前面谈的是为注意力保留空间，这一段把它具体化为「${chapter.idea}」：界面负责保持线索，读者决定何时前进。`
          : `这是原型的预设回复，尚未连接真实 AI。关于「${chapter.title}」，可以先抓住这条线索：${chapter.idea} 正式接入后，这里会加载宿主对你问题的实际回答。`;
    this.messages.push(
      { messageId: `question-${++this.sequence}`, chunkId: input.receipt.chunkId, role: "user", content: question },
      { messageId: `answer-${this.sequence}`, chunkId: input.receipt.chunkId, role: "assistant", content: answer },
    );
    return readerSuccess(this.snapshot());
  }
}
