import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { mockApi } from '../../test/mockApi';
import SearchChat from './SearchChat';

async function ask(user, question) {
  await user.type(screen.getByLabelText('Ask a question about your claims'), question);
  await user.click(screen.getByRole('button', { name: 'Send question' }));
}

describe('SearchChat', () => {
  it('shows the backend error instead of a canned answer, and can retry', async () => {
    let attempts = 0;
    const requests = mockApi({
      'POST /rag/query': () => {
        attempts += 1;
        return attempts === 1
          ? { status: 503, data: { detail: 'AI provider is not configured on this server' } }
          : { data: { answer: 'Two claims exceed $50,000.', source_documents: [] } };
      },
    });
    const user = userEvent.setup();
    render(<SearchChat />);

    await ask(user, 'Which claims are over $50,000?');

    const error = await screen.findByRole('alert');
    expect(error).toHaveTextContent('The search failed');
    expect(error).toHaveTextContent('AI provider is not configured on this server');
    expect(screen.queryByText(/Lumbar Disc Herniation/)).not.toBeInTheDocument();
    expect(requests[0].body).toEqual({ question: 'Which claims are over $50,000?', top_k: 5 });

    await user.click(screen.getByRole('button', { name: /try again/i }));

    expect(await screen.findByText('Two claims exceed $50,000.')).toBeInTheDocument();
    expect(requests).toHaveLength(2);
  });

  it('labels answers produced by the mock LLM', async () => {
    mockApi({
      'POST /rag/query': {
        data: {
          answer: 'Mock answer.',
          source: 'mock',
          source_documents: [{ doc_id: 'doc-7', text_snippet: 'Invoice total', score: 0.87 }],
        },
      },
    });
    const user = userEvent.setup();
    render(<SearchChat />);

    await ask(user, 'Summarize the invoices');

    expect(await screen.findByText('Mock answer.')).toBeInTheDocument();
    expect(screen.getByText('Mock AI')).toBeInTheDocument();
    expect(screen.getByText('doc-7')).toBeInTheDocument();
    expect(screen.getByText('87%')).toBeInTheDocument();
  });
});
