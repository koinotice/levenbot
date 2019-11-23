import math
import bitstring
from math import floor, log2
from struct import pack

from .jubjub import Point, EtecPoint, JUBJUB_L, JUBJUB_C
from .field import FQ


MAX_SEGMENT_BITS = floor(log2(JUBJUB_L))
MAX_SEGMENT_BYTES = MAX_SEGMENT_BITS // 8

BASE_POINTS = [
	Point(x=FQ(17434558536782967610340762605448133754549234172198748128207635616973179917758),
			y=FQ(13809929214859773185494095338070573446620668786591540427529120055108311408601)).as_etec(),
	Point(x=FQ(20881191793028387546033104172192345421491262837680372142491907592652070161952),
			y=FQ(5075784556128217284685225562241792312450302661801014564715596050958001884858)).as_etec(),
	Point(x=FQ(8520090440088786753637148399502745058630978778520003292078671435389456269403),
			y=FQ(19065955179398565181112355398967936758982488978618882004783674372269664446856)).as_etec(),
	Point(x=FQ(8252178246422932554470545827089444002049004598962888144864423033128179910983),
			y=FQ(15651909989309155104946748757069215505870124528799433233405947236802744549198)).as_etec(),
	Point(x=FQ(19613701345946521139252906631403624319214524383237318926155152603812484828018),
			y=FQ(21617320264895522741112711536582628848652483577841815747293999179732881991324)).as_etec(),
	Point(x=FQ(6155843579522854755336642611280808148477209989679852488581779041749546316723),
			y=FQ(15124604226542856727295916283584414325323133979788055132476373290093561626104)).as_etec(),
	Point(x=FQ(2255552864031882424600016198277712968759818455778666488135834801088901251869),
			y=FQ(20183282562651407227856572417097745017658254303953678131504564910170801603804)).as_etec(),
	Point(x=FQ(6469785718442780390486680321473277194625672464989021922834954388533973416947),
			y=FQ(5600720436353295795527652424649353386087879374665126501551955649891196987168)).as_etec(),
	Point(x=FQ(19822747198989782322000510862227895356015581531461191546205046465967845769480),
			y=FQ(3800393707849833921842859875819017737993884042392479832962251554847033783794)).as_etec(),
	Point(x=FQ(13192756298671850790699683040215548099827079575802906088020686947302693197590),
			y=FQ(15505416863289104356092986110151912620791488195851478629191143516742613361168)).as_etec(),
	Point(x=FQ(18560102673687823485116829139621115053143552521166551213701801882562371217282),
			y=FQ(10307434402517116643130434991160224925935404048340663697789562678353393350945)).as_etec(),
	Point(x=FQ(2057772344621474045072424942625594353543824932258082979347356401434340603339),
			y=FQ(9271962792672945572461177416070781404722535683304151725175708012818363437950)).as_etec(),
	Point(x=FQ(20589488268290330549487301059545065722105705099391877301332342708330102762332),
			y=FQ(8026770410252218549640047551737281865893246496274084280073418895088798333026)).as_etec(),
	Point(x=FQ(21689055109037706594381163816282145658696264799278562188804299288500663789636),
			y=FQ(9723117501871279186268866962492259704047086485378031232534349179916320302814)).as_etec(),
	Point(x=FQ(8022608026033626000482912711103520220925497334883774048025153383963877259835),
			y=FQ(4493789842837389901981752813600418331832103036167110840525806584079293941456)).as_etec(),
	Point(x=FQ(515135128122729621648366388679009614561392702855117581489845826368034708957),
			y=FQ(18817782348396407942458487293128606527632521505005672364341874932095389458519)).as_etec()
]

def pedersen_hash_basepoint(name, i):
	"""
	get a base point for use with the windowed pedersen hash function.
	Before we use hash as seed to generate the base point. But to align
	with srv impl, we need to hardcode these points.
	"""
	assert(i < len(BASE_POINTS)) #align with beta2 impl
	return BASE_POINTS[i%len(BASE_POINTS)]

def pedersen_hash_windows(name, windows):
	# 62 is defined in the ZCash Sapling Specification, Theorem 5.4.1
	# See: https://github.com/HarryR/ethsnarks/issues/121#issuecomment-499441289
	n_windows = 62
	result = EtecPoint.infinity()
	for j, window in enumerate(windows):
		if j % n_windows == 0:
			current = pedersen_hash_basepoint(name, j//n_windows)
		j = j % n_windows
		if j != 0:
			current = current.double().double().double().double()
		segment = current * ((window & 0b11) + 1)
		if window > 0b11:
			segment = segment.neg()
		result += segment
	return result.as_point()


def pedersen_hash_bits(name, bits):
	# Split into 3 bit windows
	if isinstance(bits, bitstring.BitArray):
		bits = bits.bin
	windows = [int(bits[i:i+3][::-1], 2) for i in range(0, len(bits), 3)]
	assert len(windows) > 0

	# Hash resulting windows
	return pedersen_hash_windows(name, windows)


def pedersen_hash_bytes(name, data):
	"""
	Hashes a sequence of bits (the message) into a point.

	The message is split into 3-bit windows after padding (via append)
	to `len(data.bits) = 0 mod 3`
	"""
	assert isinstance(data, bytes)
	assert len(data) > 0

	# Decode bytes to octets of binary bits
	bits = ''.join([bin(_)[2:].rjust(8, '0') for _ in data])

	return pedersen_hash_bits(name, bits)


def pedersen_hash_scalars(name, *scalars):
	"""
	Calculates a pedersen hash of scalars in the same way that zCash
	is doing it according to: ... of their spec.
	It is looking up 3bit chunks in a 2bit table (3rd bit denotes sign).

	E.g:

		(b2, b1, b0) = (1,0,1) would look up first element and negate it.

	Row i of the lookup table contains:

		[2**4i * base, 2 * 2**4i * base, 3 * 2**4i * base, 3 * 2**4i * base]

	E.g:

		row_0 = [base, 2*base, 3*base, 4*base]
		row_1 = [16*base, 32*base, 48*base, 64*base]
		row_2 = [256*base, 512*base, 768*base, 1024*base]

	Following Theorem 5.4.1 of the zCash Sapling specification, for baby jub_jub
	we need a new base point every 62 windows. We will therefore have multiple
	tables with 62 rows each.
	"""
	windows = []
	for i, s in enumerate(scalars):
		windows += list((s >> i) & 0b111 for i in range(0,s.bit_length(),3))
	return pedersen_hash_windows(name, windows)
