"""Tag filtering across the memory stores."""

from silhouette.storage._tags import matches_tags, normalize_tags


def test_sin_etiquetas_pedidas_pasa_todo():
    assert matches_tags(["a", "b"], []) is True
    assert matches_tags([], []) is True


def test_pasa_si_comparte_al_menos_una():
    assert matches_tags(["carla", "prensa"], ["carla"]) is True
    assert matches_tags(["carla", "prensa"], ["diego", "prensa"]) is True


def test_no_pasa_si_no_comparte_ninguna():
    assert matches_tags(["diego"], ["carla"]) is False
    assert matches_tags([], ["carla"]) is False


def test_normalizacion():
    assert normalize_tags(None) == ()
    assert normalize_tags([" carla ", "", "carla", "diego"]) == ("carla", "diego")
