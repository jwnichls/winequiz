var grape_api_url = "/api/v1/grapes"
var country_api_url = "/api/v1/countries"

function get_grapes(callback) {
    $.getJSON(grape_api_url, function(data) {
        // Make options with grape as name and ID as value
        if (data.grapes) {
			_grapes = data.grapes;
			callback(_grapes);
        }
    })		
}

function get_countries(callback) {
    $.getJSON(country_api_url, function(data) {
        // Make options with grape as name and ID as value
        if (data.countries) {
			_countries = data.countries;
			callback(_countries);
        }			
    })
}
