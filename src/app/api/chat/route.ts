import { NextRequest, NextResponse } from "next/server";
import { generateChatResponse } from "@/lib/gemini";

export async function POST(request: NextRequest) {
  try {
    if (!process.env.GEMINI_API_KEY) {
      return NextResponse.json(
        { error: "GEMINI_API_KEY is not configured. Please add it to .env.local" },
        { status: 500 }
      );
    }

    let body: unknown;

    try {
      body = await request.json();
    } catch {
      return NextResponse.json(
        { error: "Request body must be valid JSON" },
        { status: 400 }
      );
    }

    if (!body || typeof body !== "object" || !("messages" in body) || !Array.isArray((body as { messages: unknown[] }).messages) || (body as { messages: unknown[] }).messages.length === 0) {
      return NextResponse.json(
        { error: "Messages array is required and must not be empty" },
        { status: 400 }
      );
    }

    const messages = (body as { messages: { role?: string; content?: unknown }[] }).messages;
    const lastMsg = messages[messages.length - 1];

    if (!lastMsg?.content || typeof lastMsg.content !== "string" || !lastMsg.content.trim()) {
      return NextResponse.json(
        { error: "Message content is required" },
        { status: 400 }
      );
    }

    const validatedMessages = messages.map((m) => ({
      role: m.role === "assistant" || m.role === "model" ? "model" : "user",
      content: String(m.content ?? ""),
    }));

    const response = await generateChatResponse(validatedMessages);

    return NextResponse.json({ content: response });
  } catch (error) {
    console.error("Chat API error:", error);

    return NextResponse.json(
      { error: "Failed to generate response. Please try again." },
      { status: 502 }
    );
  }
}
