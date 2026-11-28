import SearchChat from '../components/RAG/SearchChat';
import PageHeader from '../components/Shared/PageHeader';

export default function RAGSearchPage() {
  return (
    <div id="rag-search-page">
      <PageHeader title="AI search" description="Ask about the claims in indexed documents. Answers cite the passages they were drawn from." />
      <SearchChat />
    </div>
  );
}
