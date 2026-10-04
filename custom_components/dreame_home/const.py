"""Constants for the read-only Dreame Home beta."""

from homeassistant.const import Platform

DOMAIN = "dreame_home"
PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR)
CONF_REGION = "region"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_VISITOR_ID = "visitor_id"
CONF_ACCOUNT_UID = "account_uid"
CONF_MQTT = "mqtt_enabled"
REGIONS = ("eu", "cn", "us", "ru", "sg", "kr", "by")
