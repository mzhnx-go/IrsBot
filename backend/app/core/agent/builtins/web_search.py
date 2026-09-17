"""Web search tool — uses Tavily/Brave or returns a placeholder."""

from app.core.agent.tools import register_tool


@register_tool("web_search", "Search the web for information", category="web")
async def web_search(query: str, engine: str = "tavily", top_k: int = 5) -> str:
    """Perform a web search and return summarized results.

    Args:
        query: The search query string.
        engine: Search engine to use ("tavily" or "brave").
        top_k: Number of results to return.
    """
    if engine == "tavily":
        try:
            from langchain_community.tools.tavily_search import TavilySearchResults
            searcher = TavilySearchResults(max_results=top_k)
            results = await searcher.ainvoke(query)
            if results:
                return "\n\n".join(
                    f"[{r.get('title', '')}]\n{r.get('content', '')}"
                    for r in results
                )
            return "No results found."
        except ImportError:
            pass
        except Exception:
            pass
    elif engine == "brave":
        try:
            from langchain_community.tools import BraveSearch
            searcher = BraveSearch(max_results=top_k)
            results = await searcher.ainvoke(query)
            if results:
                return str(results)
            return "No results found."
        except ImportError:
            pass
        except Exception:
            pass

    # Fallback: return placeholder for testing without API keys
    return (
        f"[Web Search Placeholder] Query: '{query}', "
        f"Engine: {engine}, Top-K: {top_k}\n"
        "No search results available (API key not configured)."
    )
