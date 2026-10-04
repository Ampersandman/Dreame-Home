"""Constants for the Dreame Home integration."""

from homeassistant.const import Platform

DOMAIN = "dreame_home"
PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.SELECT,
             Platform.NUMBER, Platform.BUTTON, Platform.VACUUM)
CONF_REGION = "region"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_VISITOR_ID = "visitor_id"
CONF_ACCOUNT_UID = "account_uid"
CONF_MQTT = "mqtt_enabled"
REGIONS = ("eu", "cn", "us", "ru", "sg", "kr", "by")
