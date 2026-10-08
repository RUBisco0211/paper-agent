import httpx

from app.platform import openalex


def test_openalex_returns_an_importable_doi_when_the_work_has_a_doi(
    monkeypatch,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "display_name": "Safety paper",
                        "doi": "https://doi.org/10.1234/example",
                        "publication_year": 2025,
                        "authorships": [],
                        "primary_location": {
                            "landing_page_url": "https://example.org/paper"
                        },
                    }
                ],
            },
        )
    )
    client_class = httpx.Client
    monkeypatch.setattr(
        openalex.httpx,
        "Client",
        lambda **kwargs: client_class(transport=transport, **kwargs),
    )

    papers = openalex.OpenAlexAdapter().search("safety", 1)

    assert papers[0]["doi"] == "10.1234/example"
