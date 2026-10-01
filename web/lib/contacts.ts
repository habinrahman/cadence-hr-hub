/**
 * The pipeline's phone finder also stores date-shaped digit runs (2023-01-01, or 20230101 once normalised) as phone
 * numbers. A date is never shown as a phone number in the interface. The stored data is left as it is.
 */
const DATE_SHAPED = /^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$/;
const COMPACT_DATE = /^20\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$/;

export function isDateShaped(value: string): boolean {
  const trimmed = value.trim();
  return DATE_SHAPED.test(trimmed) || COMPACT_DATE.test(trimmed);
}

export function realPhones(contacts: { kind: string; value: string }[]): string[] {
  return contacts.filter((c) => c.kind === "phone" && !isDateShaped(c.value)).map((c) => c.value);
}

/** Contacts as they should be listed: emails and real phone numbers, no dates posing as phones. */
export function displayContacts<T extends { kind: string; value: string }>(contacts: T[]): T[] {
  return contacts.filter((c) => !(c.kind === "phone" && isDateShaped(c.value)));
}
