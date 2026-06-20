from kimp3.strings_operations import album_title_similarity, split_album_title


def test_split_album_title_extracts_trailing_parenthetical_qualifier():
    assert split_album_title("The Information (Deluxe Edition)") == (
        "The Information",
        "Deluxe Edition",
    )


def test_album_title_similarity_weights_base_title_above_parentheses():
    query = "The Information (Deluxe Edition)"

    assert album_title_similarity("The Information (Deluxe Version)", query) > 0
    assert album_title_similarity("Guero (Deluxe Edition)", query) == 0
    assert album_title_similarity(
        "The Information (Deluxe Version)", query
    ) > album_title_similarity("Guero (Deluxe Edition)", query)


def test_album_title_similarity_accepts_missing_qualifier_for_same_album():
    assert (
        album_title_similarity("The Information", "The Information (Deluxe Edition)")
        > 0
    )
