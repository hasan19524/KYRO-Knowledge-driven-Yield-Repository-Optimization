import { GoogleGenerativeAI } from "@google/generative-ai";

export function getGeminiClient() {
  const apiKey = process.env.GEMINI_API_KEY;

  if (!apiKey) {
    throw new Error("GEMINI_API_KEY is not set in environment variables");
  }

  return new GoogleGenerativeAI(apiKey);
}

export async function generateChatResponse(
  messages: { role: string; content: string }[]
): Promise<string> {
  const genAI = getGeminiClient();
  const model = genAI.getGenerativeModel({ model: "gemini-3.6-flash" });

  const chat = model.startChat({
    history: messages.slice(0, -1).map((m) => ({
      role: m.role === "assistant" || m.role === "model" ? "model" : "user",
      parts: [{ text: String(m.content ?? "") }],
    })),
    generationConfig: {
      temperature: 0.7,
      maxOutputTokens: 8192,
    },
  });

  const lastMessage = messages[messages.length - 1];

  if (!lastMessage?.content || typeof lastMessage.content !== "string" || !lastMessage.content.trim()) {
    throw new Error("Message content is required");
  }

  const result = await chat.sendMessage(lastMessage.content);
  return result.response.text();
}
