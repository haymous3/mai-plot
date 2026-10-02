import { NextRequest, NextResponse } from 'next/server';

import { documentServiceUrl } from '@/lib/api';
import { ACCESS_COOKIE } from '@/lib/auth';

/**
 * Streams a document through to the reviewer's viewer (SCRUM-192). Reads the
 * httpOnly cookie token and proxies document-service
 * GET /admin/documents/{id}/file, passing the bytes straight back — the object
 * is never exposed via a public or pre-signed URL, and access stays auth-gated
 * end to end. Mirrors the PoA document proxy (SCRUM-61).
 *
 * Note this is NOT /api/documents/personal/{id}/view: that one serves the
 * owner their own document and only when verified. A reviewer needs the
 * unverified ones, which is the whole point of the admin route behind this.
 *
 * Errors (SCRUM-239): the review modal loads this route in an <iframe>, so a
 * JSON error body was rendered verbatim — reviewers saw
 * `{"error":"DOCUMENT_NOT_FOUND"}`. A browsing request (Accept: text/html) now
 * gets a short readable page; anything else still gets JSON. The messages are
 * fixed strings — nothing from the request or the backend is interpolated.
 */

const ERROR_MESSAGES: Record<string, { title: string; detail: string }> = {
  DOCUMENT_NOT_FOUND: {
    title: 'File missing',
    detail:
      'This document has a record but its file is not in storage — it was uploaded before file storage was set up, or never uploaded. Ask the uploader to upload it again, or reject it with a note.',
  },
  DOCUMENT_STORAGE_UNAVAILABLE: {
    title: 'Storage unavailable',
    detail: 'File storage did not respond. Close this and try again in a moment.',
  },
  BACKEND_UNAVAILABLE: {
    title: 'Service unavailable',
    detail: 'The document service did not respond. Close this and try again in a moment.',
  },
  NO_SESSION: {
    title: 'Session expired',
    detail: 'Sign in to the admin console again, then reopen this document.',
  },
};

const FALLBACK_MESSAGE = {
  title: 'Could not open this document',
  detail: 'Close this and try again. If it keeps happening, the file may need to be re-uploaded.',
};

function errorResponse(request: NextRequest, code: string, status: number): NextResponse {
  if (!(request.headers.get('accept') ?? '').includes('text/html')) {
    return NextResponse.json({ error: code }, { status });
  }
  const { title, detail } =
    ERROR_MESSAGES[code] ?? (status === 401 || status === 403 ? ERROR_MESSAGES.NO_SESSION : FALLBACK_MESSAGE);
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${title}</title></head>
<body style="margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center;font-family:system-ui,sans-serif;background:#f7f7f5;color:#1f2937">
<div style="max-width:28rem;padding:2rem;text-align:center"><h1 style="font-size:1.125rem;margin:0 0 .5rem">${title}</h1>
<p style="margin:0;font-size:.875rem;line-height:1.5;color:#4b5563">${detail}</p></div></body></html>`;
  return new NextResponse(html, {
    status,
    headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'private, no-store' },
  });
}

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const token = request.cookies.get(ACCESS_COOKIE)?.value;
  if (!token) {
    return errorResponse(request, 'NO_SESSION', 401);
  }

  // Only ever the two known values — an unrecognised source is not forwarded,
  // so a crafted query string cannot probe the backend's routing.
  const requested = request.nextUrl.searchParams.get('source');
  const source = requested === 'personal' ? 'personal' : 'listing';

  let resp: Response;
  try {
    resp = await fetch(
      `${documentServiceUrl()}/admin/documents/${params.id}/file?source=${source}`,
      {
        headers: { authorization: `Bearer ${token}` },
        cache: 'no-store',
      },
    );
  } catch {
    return errorResponse(request, 'BACKEND_UNAVAILABLE', 502);
  }

  if (!resp.ok) {
    let code = 'DOCUMENT_FAILED';
    try {
      const body = (await resp.json()) as { error_code?: string };
      if (body.error_code) code = body.error_code;
    } catch {
      // keep default
    }
    return errorResponse(request, code, resp.status);
  }

  const body = await resp.arrayBuffer();
  return new NextResponse(body, {
    status: 200,
    headers: {
      'content-type': resp.headers.get('content-type') ?? 'application/octet-stream',
      // Render inline in the viewer; never index or cache a private document.
      'content-disposition': 'inline',
      'cache-control': 'private, no-store',
      // The backend already pins the content type to pdf/jpeg/png; repeat
      // nosniff here because this response is what the browser actually sees.
      'x-content-type-options': 'nosniff',
    },
  });
}
