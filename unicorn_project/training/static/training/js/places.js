// unicorn_project/training/static/training/js/places.js

(function(){
  function log(){ try { console.log.apply(console, ['[places]', ...arguments]); } catch(e){} }

  function extractAddressComponents(place){
    const get = (type, want='long_name') => {
      const c = place.address_components?.find(x => x.types.includes(type));
      return c ? c[want] : '';
    };
    const streetNumber = get('street_number');
    const route        = get('route');
    const postalTown   = get('postal_town');
    const locality     = get('locality');
    const town         = postalTown || locality;
    const postcode     = get('postal_code');

    let street = [streetNumber, route].filter(Boolean).join(' ');
    if (!street && place.name && route) street = `${place.name} ${route}`;
    return { street, town, postcode };
  }

  function attachAutocompleteTo(addressInput) {
    if (!addressInput) return;
    const townInput = document.querySelector('#id_town');
    const postInput = document.querySelector('#id_postcode');

    function bind() {
      if (!(window.google && google.maps && google.maps.places)) {
        // wait for Google to be ready
        return setTimeout(bind, 150);
      }
      const ac = new google.maps.places.Autocomplete(addressInput, {
        fields: ['address_components','formatted_address','name'],
        types: ['address'],
        componentRestrictions: { country: 'gb' }
      });
      ac.addListener('place_changed', function(){
        const place = ac.getPlace();
        const { street, town, postcode } = extractAddressComponents(place);
        if (street)   addressInput.value = street;
        if (town && townInput)     townInput.value = town;
        if (postcode && postInput) postInput.value = postcode;
      });
      log('Autocomplete attached to', addressInput);
    }
    bind();
  }

  function initOnPage() {
    // Any form that has address_line/town/postcode with standard Django ids
    const addr = document.querySelector('#id_address_line');
    if (addr) attachAutocompleteTo(addr);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initOnPage);
  } else {
    initOnPage();
  }

  // also react when Google script finishes
  document.addEventListener('gmaps:ready', initOnPage);
})();
