"""No-show grace period and Extra details on the Store Details page (Phase 5a).

The page now owns these two fields, so the owner no longer needs the modal on /owner/ to edit them.
Rules under test:
- extras are only written when the request carries `extras_present` (the page's own marker), so a
  client that does not have the Extra details section can never wipe them by accident
- an empty grace field keeps the current value; an invalid value saves nothing at all
"""

from django.urls import reverse

from restaurants.forms import MAX_EXTRAS
from restaurants.models import Restaurant

from . import test_store_details_save as base
from .store_test_utils import OLD_URL


class ExtrasPageRenderTests(base.StoreDetailsSaveBase):
    def test_page_shows_current_grace_period_and_extras(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('name="no_show_grace_minutes"', html)
        self.assertIn('value="45"', html)
        self.assertIn('name="extras_present"', html)
        self.assertIn('name="extra_key"', html)
        self.assertIn('value="Parking"', html)
        self.assertIn('value="Yes"', html)

    def test_extras_are_escaped_in_the_page(self):
        self.store.extra_details = [{"key": '"><script>x</script>', "value": "<b>v</b>"}]
        self.store.save()
        html = self.client.get(self.url).content.decode()
        self.assertNotIn("<script>x</script>", html)
        self.assertNotIn("<b>v</b>", html)

    def test_add_button_is_disabled_when_the_limit_is_reached(self):
        self.store.extra_details = [{"key": f"k{i}", "value": f"v{i}"} for i in range(MAX_EXTRAS)]
        self.store.save()
        html = self.client.get(self.url).content.decode()
        add_button = html.split("data-add-extra", 1)[1].split(">", 1)[0]
        self.assertIn("disabled", add_button)

    def test_add_button_is_enabled_below_the_limit(self):
        html = self.client.get(self.url).content.decode()
        add_button = html.split("data-add-extra", 1)[1].split(">", 1)[0]
        self.assertNotIn("disabled", add_button)


class SaveExtrasTests(base.StoreDetailsSaveBase):
    def save_extras(self, keys, values, **fields):
        return self.post(
            extras_present="1", extra_key=keys, extra_value=values, **fields
        )

    def test_extras_are_replaced_with_the_posted_rows(self):
        self.save_extras(["Wifi", "Pets"], ["Free", "Welcome"])
        self.store.refresh_from_db()
        self.assertEqual(
            self.store.extra_details,
            [{"key": "Wifi", "value": "Free"}, {"key": "Pets", "value": "Welcome"}],
        )

    def test_removing_every_row_clears_the_extras(self):
        response = self.post(extras_present="1")
        self.assertEqual(response.status_code, 302)
        self.store.refresh_from_db()
        self.assertEqual(self.store.extra_details, [])

    def test_extras_are_kept_when_the_request_has_no_marker(self):
        # a client without the Extra details section (no extras_present) must not wipe them
        self.post(extra_key=["Wifi"], extra_value=["Free"])
        self.store.refresh_from_db()
        self.assertEqual(self.store.extra_details, [{"key": "Parking", "value": "Yes"}])

    def test_incomplete_rows_are_dropped(self):
        self.save_extras(["Wifi", "", "Pets"], ["Free", "orphan value", ""])
        self.store.refresh_from_db()
        self.assertEqual(self.store.extra_details, [{"key": "Wifi", "value": "Free"}])

    def test_rows_over_the_limit_are_cut(self):
        count = MAX_EXTRAS + 3
        self.save_extras([f"k{i}" for i in range(count)], [f"v{i}" for i in range(count)])
        self.store.refresh_from_db()
        self.assertEqual(len(self.store.extra_details), MAX_EXTRAS)

    def test_long_values_are_trimmed_by_the_server(self):
        self.save_extras(["k" * 100], ["v" * 300])
        self.store.refresh_from_db()
        self.assertEqual(len(self.store.extra_details[0]["key"]), 60)
        self.assertEqual(len(self.store.extra_details[0]["value"]), 200)

    def test_extras_saved_together_with_other_fields(self):
        self.save_extras(["Wifi"], ["Free"], name="Renamed", phone="+66 2 000 0000")
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "Renamed")
        self.assertEqual(self.store.phone, "+66 2 000 0000")
        self.assertEqual(self.store.extra_details, [{"key": "Wifi", "value": "Free"}])

    def test_json_success_returns_what_was_actually_saved(self):
        payload = self.save_extras(
            ["Wifi", "", "Pets"], ["Free", "orphan", ""], ajax=True, no_show_grace_minutes="20"
        ).json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["extras"], [{"key": "Wifi", "value": "Free"}])
        self.assertEqual(payload["no_show_grace_minutes"], 20)


class SaveGraceMinutesTests(base.StoreDetailsSaveBase):
    def test_grace_period_is_saved(self):
        self.post(no_show_grace_minutes="60")
        self.store.refresh_from_db()
        self.assertEqual(self.store.no_show_grace_minutes, 60)

    def test_zero_is_a_real_value(self):
        self.post(no_show_grace_minutes="0")
        self.store.refresh_from_db()
        self.assertEqual(self.store.no_show_grace_minutes, 0)

    def test_blank_keeps_the_current_value(self):
        self.post(no_show_grace_minutes="")
        self.store.refresh_from_db()
        self.assertEqual(self.store.no_show_grace_minutes, 45)

    def test_out_of_range_or_non_numeric_values_are_rejected(self):
        for bad in ("241", "-1", "abc", "1.5"):
            with self.subTest(value=bad):
                response = self.post(ajax=True, no_show_grace_minutes=bad)
                self.assertEqual(response.status_code, 400)
                self.assertIn("no_show_grace_minutes", response.json()["errors"])
                self.store.refresh_from_db()
                self.assertEqual(self.store.no_show_grace_minutes, 45)

    def test_invalid_grace_saves_nothing_else(self):
        response = self.post(
            ajax=True, name="Should not save", no_show_grace_minutes="999",
            extras_present="1", extra_key=["Wifi"], extra_value=["Free"],
        )
        self.assertEqual(response.status_code, 400)
        self.assert_store_untouched()
        self.store.refresh_from_db()
        self.assertEqual(self.store.extra_details, [{"key": "Parking", "value": "Yes"}])

    def test_invalid_form_does_not_clear_extras(self):
        self.post(ajax=True, name="", extras_present="1")
        self.store.refresh_from_db()
        self.assertEqual(self.store.extra_details, [{"key": "Parking", "value": "Yes"}])


class NoJavascriptRerenderTests(base.StoreDetailsSaveBase):
    def test_rerender_keeps_what_the_owner_typed(self):
        response = self.post(
            name="", no_show_grace_minutes="999", extras_present="1",
            extra_key=["Wifi", "Half row"], extra_value=["Free", ""],
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('value="999"', html)
        self.assertIn('value="Wifi"', html)
        self.assertIn('value="Half row"', html)  # incomplete row is shown again, not silently lost
        self.assertNotIn('value="Parking"', html)  # typed rows replace the saved ones
        self.assert_store_untouched()


class ModalEditStillWorksWithPhase5aTests(base.StoreDetailsSaveBase):
    """The old modal on /owner/ still posts to store_update with its own extras handling."""

    def test_modal_edit_still_replaces_extras_and_grace(self):
        self.client.post(
            reverse("owner_store_update", args=[self.store.slug]),
            {
                "name": "Baan Suan", "category": "Café", "address": "1 Old Rd", "image": OLD_URL,
                "no_show_grace_minutes": "15", "extra_key": ["Wifi"], "extra_value": ["Free"],
            },
        )
        self.store.refresh_from_db()
        self.assertEqual(self.store.no_show_grace_minutes, 15)
        self.assertEqual(self.store.extra_details, [{"key": "Wifi", "value": "Free"}])
        self.assertEqual(Restaurant.objects.filter(owner=self.owner).count(), 1)
