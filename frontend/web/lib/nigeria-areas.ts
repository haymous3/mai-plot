/**
 * Nigerian areas with approximate centre coordinates — for a realtor's base
 * location (SCRUM-214). Pure: no network, no geocoder.
 *
 * WHY A BUILT-IN LIST. Proximity assignment searches within 50 km of a
 * property, so an area's centre is precise enough, and picking from a list
 * means no address is sent to a geocoding provider outside Nigeria (§9) and no
 * API key is needed. Coordinates are approximate area centres (to ~0.01°, about
 * a kilometre) — good for a 50 km radius, not for navigation.
 *
 * Coverage: every state capital (plus a second city where a state has one of
 * comparable size), and finer areas for the V1 launch markets — Lagos, the FCT
 * and Rivers — where a realtor's side of the city genuinely changes which
 * properties are in range. Adding an area is adding a line.
 */

export type Area = { state: string; area: string; lat: number; lng: number };

export const AREAS: readonly Area[] = [
  // Lagos — V1 market
  { state: 'Lagos', area: 'Ikeja', lat: 6.6018, lng: 3.3515 },
  { state: 'Lagos', area: 'Lekki', lat: 6.4698, lng: 3.5852 },
  { state: 'Lagos', area: 'Ajah', lat: 6.4667, lng: 3.5667 },
  { state: 'Lagos', area: 'Sangotedo', lat: 6.47, lng: 3.64 },
  { state: 'Lagos', area: 'Ibeju-Lekki', lat: 6.45, lng: 3.85 },
  { state: 'Lagos', area: 'Victoria Island', lat: 6.4281, lng: 3.4219 },
  { state: 'Lagos', area: 'Ikoyi', lat: 6.452, lng: 3.435 },
  { state: 'Lagos', area: 'Lagos Island', lat: 6.4541, lng: 3.3947 },
  { state: 'Lagos', area: 'Apapa', lat: 6.45, lng: 3.3667 },
  { state: 'Lagos', area: 'Surulere', lat: 6.5, lng: 3.35 },
  { state: 'Lagos', area: 'Yaba', lat: 6.5095, lng: 3.3711 },
  { state: 'Lagos', area: 'Gbagada', lat: 6.55, lng: 3.39 },
  { state: 'Lagos', area: 'Maryland', lat: 6.57, lng: 3.37 },
  { state: 'Lagos', area: 'Oshodi', lat: 6.553, lng: 3.343 },
  { state: 'Lagos', area: 'Festac', lat: 6.4667, lng: 3.2833 },
  { state: 'Lagos', area: 'Alimosho', lat: 6.61, lng: 3.29 },
  { state: 'Lagos', area: 'Ikorodu', lat: 6.6194, lng: 3.5105 },
  { state: 'Lagos', area: 'Epe', lat: 6.5833, lng: 3.9833 },
  { state: 'Lagos', area: 'Badagry', lat: 6.4167, lng: 2.8833 },
  // FCT — V1 market
  { state: 'FCT (Abuja)', area: 'Garki', lat: 9.0333, lng: 7.4833 },
  { state: 'FCT (Abuja)', area: 'Maitama', lat: 9.0833, lng: 7.4983 },
  { state: 'FCT (Abuja)', area: 'Wuse', lat: 9.08, lng: 7.47 },
  { state: 'FCT (Abuja)', area: 'Asokoro', lat: 9.04, lng: 7.52 },
  { state: 'FCT (Abuja)', area: 'Jabi', lat: 9.07, lng: 7.42 },
  { state: 'FCT (Abuja)', area: 'Gwarinpa', lat: 9.11, lng: 7.4 },
  { state: 'FCT (Abuja)', area: 'Kubwa', lat: 9.15, lng: 7.33 },
  { state: 'FCT (Abuja)', area: 'Lugbe', lat: 8.98, lng: 7.37 },
  { state: 'FCT (Abuja)', area: 'Lokogoma', lat: 8.98, lng: 7.46 },
  { state: 'FCT (Abuja)', area: 'Kuje', lat: 8.88, lng: 7.23 },
  { state: 'FCT (Abuja)', area: 'Gwagwalada', lat: 8.94, lng: 7.08 },
  { state: 'FCT (Abuja)', area: 'Bwari', lat: 9.28, lng: 7.38 },
  // Rivers — V1 market
  { state: 'Rivers', area: 'Port Harcourt', lat: 4.8156, lng: 7.0498 },
  { state: 'Rivers', area: 'Port Harcourt GRA', lat: 4.82, lng: 7.01 },
  { state: 'Rivers', area: 'Trans-Amadi', lat: 4.81, lng: 7.04 },
  { state: 'Rivers', area: 'Rumuokoro', lat: 4.87, lng: 6.99 },
  { state: 'Rivers', area: 'Obio-Akpor', lat: 4.85, lng: 6.97 },
  { state: 'Rivers', area: 'Eleme', lat: 4.79, lng: 7.12 },
  { state: 'Rivers', area: 'Bonny', lat: 4.45, lng: 7.17 },
  // Every other state — capital, and a second major city where one exists
  { state: 'Abia', area: 'Umuahia', lat: 5.525, lng: 7.49 },
  { state: 'Abia', area: 'Aba', lat: 5.1066, lng: 7.3667 },
  { state: 'Adamawa', area: 'Yola', lat: 9.2035, lng: 12.4954 },
  { state: 'Akwa Ibom', area: 'Uyo', lat: 5.0377, lng: 7.9128 },
  { state: 'Anambra', area: 'Awka', lat: 6.2104, lng: 7.0741 },
  { state: 'Anambra', area: 'Onitsha', lat: 6.1449, lng: 6.7857 },
  { state: 'Bauchi', area: 'Bauchi', lat: 10.3158, lng: 9.8442 },
  { state: 'Bayelsa', area: 'Yenagoa', lat: 4.9267, lng: 6.2676 },
  { state: 'Benue', area: 'Makurdi', lat: 7.7322, lng: 8.5391 },
  { state: 'Borno', area: 'Maiduguri', lat: 11.8333, lng: 13.15 },
  { state: 'Cross River', area: 'Calabar', lat: 4.9757, lng: 8.3417 },
  { state: 'Delta', area: 'Asaba', lat: 6.198, lng: 6.733 },
  { state: 'Delta', area: 'Warri', lat: 5.5167, lng: 5.75 },
  { state: 'Ebonyi', area: 'Abakaliki', lat: 6.3249, lng: 8.1137 },
  { state: 'Edo', area: 'Benin City', lat: 6.335, lng: 5.6037 },
  { state: 'Ekiti', area: 'Ado-Ekiti', lat: 7.6211, lng: 5.2214 },
  { state: 'Enugu', area: 'Enugu', lat: 6.4584, lng: 7.5464 },
  { state: 'Gombe', area: 'Gombe', lat: 10.2897, lng: 11.1673 },
  { state: 'Imo', area: 'Owerri', lat: 5.4836, lng: 7.0333 },
  { state: 'Jigawa', area: 'Dutse', lat: 11.7564, lng: 9.3386 },
  { state: 'Kaduna', area: 'Kaduna', lat: 10.5105, lng: 7.4165 },
  { state: 'Kaduna', area: 'Zaria', lat: 11.0855, lng: 7.7199 },
  { state: 'Kano', area: 'Kano', lat: 12.0022, lng: 8.592 },
  { state: 'Katsina', area: 'Katsina', lat: 12.9908, lng: 7.6018 },
  { state: 'Kebbi', area: 'Birnin Kebbi', lat: 12.4539, lng: 4.1975 },
  { state: 'Kogi', area: 'Lokoja', lat: 7.8023, lng: 6.7333 },
  { state: 'Kwara', area: 'Ilorin', lat: 8.4966, lng: 4.5421 },
  { state: 'Nasarawa', area: 'Lafia', lat: 8.4939, lng: 8.5153 },
  { state: 'Nasarawa', area: 'Karu / Mararaba', lat: 9.02, lng: 7.6 },
  { state: 'Niger', area: 'Minna', lat: 9.6139, lng: 6.5569 },
  { state: 'Ogun', area: 'Abeokuta', lat: 7.1475, lng: 3.3619 },
  { state: 'Ogun', area: 'Sango-Ota', lat: 6.69, lng: 3.23 },
  { state: 'Ogun', area: 'Ijebu-Ode', lat: 6.82, lng: 3.92 },
  { state: 'Ondo', area: 'Akure', lat: 7.2571, lng: 5.2058 },
  { state: 'Osun', area: 'Osogbo', lat: 7.7827, lng: 4.5418 },
  { state: 'Osun', area: 'Ile-Ife', lat: 7.4667, lng: 4.5667 },
  { state: 'Oyo', area: 'Ibadan', lat: 7.3775, lng: 3.947 },
  { state: 'Oyo', area: 'Ogbomosho', lat: 8.1333, lng: 4.25 },
  { state: 'Plateau', area: 'Jos', lat: 9.8965, lng: 8.8583 },
  { state: 'Sokoto', area: 'Sokoto', lat: 13.0059, lng: 5.2476 },
  { state: 'Taraba', area: 'Jalingo', lat: 8.8937, lng: 11.3597 },
  { state: 'Yobe', area: 'Damaturu', lat: 11.747, lng: 11.9608 },
  { state: 'Zamfara', area: 'Gusau', lat: 12.1628, lng: 6.6614 },
];

/** Every state, in the order a Nigerian user expects: launch markets first. */
export function states(): string[] {
  const launch = ['Lagos', 'FCT (Abuja)', 'Rivers'];
  const rest = [...new Set(AREAS.map((a) => a.state))]
    .filter((s) => !launch.includes(s))
    .sort((a, b) => a.localeCompare(b));
  return [...launch, ...rest];
}

export function areasIn(state: string): Area[] {
  return AREAS.filter((a) => a.state === state);
}

// Mirrors realtor-service's validate_base_location, so the browser can refuse
// a location the server would reject before anything is sent.
export function isInNigeria(lat: number, lng: number): boolean {
  return lat >= 4.0 && lat <= 14.0 && lng >= 2.5 && lng <= 15.0;
}

function distanceKm(aLat: number, aLng: number, bLat: number, bLng: number): number {
  const rad = Math.PI / 180;
  const dLat = (bLat - aLat) * rad;
  const dLng = (bLng - aLng) * rad;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(aLat * rad) * Math.cos(bLat * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}

/** The listed area closest to a coordinate — how a stored base is described
 * ("Near Lekki, Lagos") without storing a label anywhere. */
export function nearestArea(lat: number, lng: number): Area & { km: number } {
  let best = AREAS[0];
  let bestKm = Infinity;
  for (const a of AREAS) {
    const km = distanceKm(lat, lng, a.lat, a.lng);
    if (km < bestKm) {
      best = a;
      bestKm = km;
    }
  }
  return { ...best, km: bestKm };
}

/** "Near Lekki, Lagos" / "In Kano" — a readable name for a stored base. */
export function describeBase(lat: number, lng: number): string {
  const near = nearestArea(lat, lng);
  const where = near.area === near.state ? near.state : `${near.area}, ${near.state}`;
  return near.km < 2 ? `In ${where}` : `Near ${where}`;
}
