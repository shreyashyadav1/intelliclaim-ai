import { FlaskConical } from 'lucide-react';
import { useApiHealth } from '../../hooks/useApiHealth';
import './Shared.css';

/**
 * Environment strip that says what the data is: every claim and document in
 * the demo workspace is synthetic, and when the backend runs MOCK_LLM the AI
 * output is mocked too.
 */
export default function DemoDataNote() {
  const { mockLlm } = useApiHealth();
  return (
    <p className="demo-note">
      <FlaskConical size={14} aria-hidden="true" />
      <span>
        {mockLlm
          ? 'Demo workspace: synthetic claims and documents, with mock AI output.'
          : 'Demo workspace: synthetic claims and documents.'}
      </span>
    </p>
  );
}
