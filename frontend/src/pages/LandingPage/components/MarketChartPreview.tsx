import { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart,
  ColorType,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  Time,
  CandlestickSeries,
  LineSeries,
  LineStyle,
  LineData,
  LineWidth,
} from 'lightweight-charts';

// Real ES daily data from May 2021 to April 2022 (252 bars)
// Shows the bull run to ATH, correction, and recovery attempt
const PREVIEW_OHLC_DATA: CandlestickData<Time>[] = [
  { time: 1620025200 as Time, open: 4181.5, high: 4202.5, low: 4181, close: 4185.75 },
  { time: 1620111600 as Time, open: 4184.25, high: 4185.5, low: 4120.5, close: 4158.25 },
  { time: 1620198000 as Time, open: 4158.25, high: 4180, low: 4153, close: 4160 },
  { time: 1620284400 as Time, open: 4158.75, high: 4197.25, low: 4140.5, close: 4194.25 },
  { time: 1620370800 as Time, open: 4197.5, high: 4232.25, low: 4191.75, close: 4225.25 },
  { time: 1620630000 as Time, open: 4226.75, high: 4238.25, low: 4172, close: 4183.5 },
  { time: 1620716400 as Time, open: 4176.75, high: 4185.5, low: 4103.75, close: 4146.25 },
  { time: 1620802800 as Time, open: 4140, high: 4150.5, low: 4051, close: 4058.75 },
  { time: 1620889200 as Time, open: 4053.5, high: 4126.75, low: 4029.25, close: 4107 },
  { time: 1620975600 as Time, open: 4112.5, high: 4178.25, low: 4105.25, close: 4169 },
  { time: 1621234800 as Time, open: 4169, high: 4178.75, low: 4136.5, close: 4157.75 },
  { time: 1621321200 as Time, open: 4159, high: 4179.5, low: 4111.5, close: 4123 },
  { time: 1621407600 as Time, open: 4114, high: 4123, low: 4055.5, close: 4111.5 },
  { time: 1621494000 as Time, open: 4107.75, high: 4169.25, low: 4084.5, close: 4154.25 },
  { time: 1621580400 as Time, open: 4152.5, high: 4185, low: 4147, close: 4151.75 },
  { time: 1621839600 as Time, open: 4151.5, high: 4206.25, low: 4142.5, close: 4193.75 },
  { time: 1621926000 as Time, open: 4199.25, high: 4212.75, low: 4179.25, close: 4185.5 },
  { time: 1622012400 as Time, open: 4188, high: 4204.25, low: 4180.5, close: 4193 },
  { time: 1622098800 as Time, open: 4193, high: 4211.5, low: 4177.75, close: 4199 },
  { time: 1622185200 as Time, open: 4211.25, high: 4217.5, low: 4201, close: 4202.5 },
  { time: 1622530800 as Time, open: 4206.5, high: 4230, low: 4190, close: 4198.5 },
  { time: 1622617200 as Time, open: 4198.5, high: 4215, low: 4190.75, close: 4206.25 },
  { time: 1622703600 as Time, open: 4208, high: 4213.25, low: 4165.25, close: 4191.25 },
  { time: 1622790000 as Time, open: 4190.75, high: 4232, low: 4177, close: 4228.25 },
  { time: 1623049200 as Time, open: 4232.25, high: 4232.5, low: 4214, close: 4225.5 },
  { time: 1623135600 as Time, open: 4227.5, high: 4236.75, low: 4205.75, close: 4225.75 },
  { time: 1623222000 as Time, open: 4225.5, high: 4235, low: 4217, close: 4218.5 },
  { time: 1623308400 as Time, open: 4222.25, high: 4249, low: 4207, close: 4238 },
  { time: 1623394800 as Time, open: 4239.5, high: 4247.75, low: 4230.75, close: 4245.75 },
  { time: 1623654000 as Time, open: 4248, high: 4257.5, low: 4233.5, close: 4254.75 },
  { time: 1623740400 as Time, open: 4246.25, high: 4258.25, low: 4228.25, close: 4236.5 },
  { time: 1623826800 as Time, open: 4238, high: 4241.5, low: 4190.25, close: 4213 },
  { time: 1623913200 as Time, open: 4204.25, high: 4222.75, low: 4183, close: 4212.25 },
  { time: 1623999600 as Time, open: 4216, high: 4220, low: 4140.75, close: 4153.5 },
  { time: 1624258800 as Time, open: 4142.5, high: 4219.75, low: 4126.75, close: 4213.75 },
  { time: 1624345200 as Time, open: 4219.25, high: 4245.5, low: 4205.75, close: 4236.25 },
  { time: 1624431600 as Time, open: 4237.5, high: 4248.25, low: 4230.5, close: 4231.5 },
  { time: 1624518000 as Time, open: 4233.75, high: 4263.75, low: 4231.75, close: 4256 },
  { time: 1624604400 as Time, open: 4262, high: 4276.75, low: 4253.5, close: 4271.25 },
  { time: 1624863600 as Time, open: 4275, high: 4282, low: 4264.25, close: 4280.5 },
  { time: 1624950000 as Time, open: 4280.5, high: 4291, low: 4271.75, close: 4282 },
  { time: 1625036400 as Time, open: 4284.75, high: 4294.25, low: 4269.25, close: 4288.5 },
  { time: 1625122800 as Time, open: 4294.25, high: 4312, low: 4286, close: 4310.75 },
  { time: 1625209200 as Time, open: 4309.75, high: 4347, low: 4308, close: 4342.75 },
  { time: 1625554800 as Time, open: 4341, high: 4348, low: 4305.25, close: 4334 },
  { time: 1625641200 as Time, open: 4328, high: 4353.25, low: 4320.25, close: 4349.75 },
  { time: 1625727600 as Time, open: 4352.25, high: 4352.25, low: 4279.25, close: 4313 },
  { time: 1625814000 as Time, open: 4310.25, high: 4364, low: 4293.25, close: 4360 },
  { time: 1626073200 as Time, open: 4362, high: 4379.25, low: 4341.75, close: 4376.5 },
  { time: 1626159600 as Time, open: 4377, high: 4383.75, low: 4356.5, close: 4361.25 },
  { time: 1626246000 as Time, open: 4359.5, high: 4384.5, low: 4350, close: 4367.75 },
  { time: 1626332400 as Time, open: 4366.5, high: 4370.25, low: 4332.5, close: 4352 },
  { time: 1626418800 as Time, open: 4347.75, high: 4368, low: 4314.25, close: 4318.5 },
  { time: 1626678000 as Time, open: 4320, high: 4320.75, low: 4224, close: 4251.25 },
  { time: 1626764400 as Time, open: 4262.75, high: 4329, low: 4252.75, close: 4315.5 },
  { time: 1626850800 as Time, open: 4318.75, high: 4355.25, low: 4310, close: 4350.5 },
  { time: 1626937200 as Time, open: 4355, high: 4371.5, low: 4341.5, close: 4359.5 },
  { time: 1627023600 as Time, open: 4371.5, high: 4408.25, low: 4367.25, close: 4403 },
  { time: 1627282800 as Time, open: 4400.5, high: 4416.75, low: 4375.5, close: 4414.25 },
  { time: 1627369200 as Time, open: 4415.75, high: 4416, low: 4364.75, close: 4394.5 },
  { time: 1627455600 as Time, open: 4380, high: 4407.75, low: 4377.5, close: 4393.75 },
  { time: 1627542000 as Time, open: 4393.75, high: 4422.5, low: 4380.5, close: 4411.75 },
  { time: 1627628400 as Time, open: 4394.25, high: 4405, low: 4370.75, close: 4389.5 },
  { time: 1627887600 as Time, open: 4396.5, high: 4419.75, low: 4377.25, close: 4379.75 },
  { time: 1627974000 as Time, open: 4383.75, high: 4417, low: 4365.25, close: 4415 },
  { time: 1628060400 as Time, open: 4409.75, high: 4415, low: 4391.25, close: 4394.75 },
  { time: 1628146800 as Time, open: 4396.25, high: 4422.75, low: 4393.75, close: 4421.5 },
  { time: 1628233200 as Time, open: 4420.25, high: 4433.25, low: 4416, close: 4429.5 },
  { time: 1628492400 as Time, open: 4428, high: 4432, low: 4412.25, close: 4425.75 },
  { time: 1628578800 as Time, open: 4427.25, high: 4438.25, low: 4416.5, close: 4430 },
  { time: 1628665200 as Time, open: 4429.25, high: 4443.25, low: 4420.75, close: 4440.5 },
  { time: 1628751600 as Time, open: 4440, high: 4456.25, low: 4430.25, close: 4454.5 },
  { time: 1628838000 as Time, open: 4455.75, high: 4463.25, low: 4451, close: 4462.5 },
  { time: 1629097200 as Time, open: 4456.25, high: 4476.5, low: 4432.5, close: 4474 },
  { time: 1629183600 as Time, open: 4472, high: 4472.25, low: 4411.75, close: 4443.5 },
  { time: 1629270000 as Time, open: 4436.75, high: 4449.75, low: 4381.5, close: 4394.5 },
  { time: 1629356400 as Time, open: 4389.75, high: 4414.75, low: 4347.75, close: 4401.5 },
  { time: 1629442800 as Time, open: 4403.75, high: 4440.5, low: 4371.75, close: 4437 },
  { time: 1629702000 as Time, open: 4435, high: 4485.75, low: 4433.5, close: 4475.5 },
  { time: 1629788400 as Time, open: 4481, high: 4492, low: 4476.75, close: 4482.5 },
  { time: 1629874800 as Time, open: 4483.5, high: 4498, low: 4476.25, close: 4493 },
  { time: 1629961200 as Time, open: 4493.75, high: 4494.25, low: 4465, close: 4466.5 },
  { time: 1630047600 as Time, open: 4470, high: 4510, low: 4462.25, close: 4505.5 },
  { time: 1630306800 as Time, open: 4508.75, high: 4534.5, low: 4500.75, close: 4525.25 },
  { time: 1630393200 as Time, open: 4529.5, high: 4542.25, low: 4512.5, close: 4520.5 },
  { time: 1630479600 as Time, open: 4527.75, high: 4540, low: 4519.25, close: 4521.25 },
  { time: 1630566000 as Time, open: 4522.5, high: 4544, low: 4516, close: 4535.25 },
  { time: 1630652400 as Time, open: 4536.75, high: 4549.5, low: 4519.25, close: 4534.5 },
  { time: 1630998000 as Time, open: 4533, high: 4548, low: 4510.75, close: 4519.25 },
  { time: 1631084400 as Time, open: 4517.5, high: 4524.75, low: 4492, close: 4512.5 },
  { time: 1631170800 as Time, open: 4511, high: 4529.5, low: 4485.5, close: 4492.25 },
  { time: 1631257200 as Time, open: 4491.25, high: 4518.25, low: 4456.5, close: 4458.25 },
  { time: 1631516400 as Time, open: 4461, high: 4492.75, low: 4444.75, close: 4469 },
  { time: 1631602800 as Time, open: 4465.75, high: 4479.5, low: 4425.25, close: 4434.75 },
  { time: 1631689200 as Time, open: 4437, high: 4477.75, low: 4427.5, close: 4472 },
  { time: 1631775600 as Time, open: 4476, high: 4478.5, low: 4433.25, close: 4464.25 },
  { time: 1631862000 as Time, open: 4459.25, high: 4472.5, low: 4406.5, close: 4421.75 },
  { time: 1632121200 as Time, open: 4411.75, high: 4418, low: 4293.75, close: 4348.25 },
  { time: 1632207600 as Time, open: 4342.5, high: 4395.75, low: 4329.25, close: 4343.25 },
  { time: 1632294000 as Time, open: 4336.5, high: 4406.5, low: 4321.25, close: 4384 },
  { time: 1632380400 as Time, open: 4386, high: 4455, low: 4385.75, close: 4438 },
  { time: 1632466800 as Time, open: 4439, high: 4453, low: 4410.75, close: 4445.75 },
  { time: 1632726000 as Time, open: 4446, high: 4472, low: 4425, close: 4433 },
  { time: 1632812400 as Time, open: 4429.75, high: 4442, low: 4334.75, close: 4343.5 },
  { time: 1632898800 as Time, open: 4347.5, high: 4378.75, low: 4344.25, close: 4349.75 },
  { time: 1632985200 as Time, open: 4360, high: 4389, low: 4294.25, close: 4297.75 },
  { time: 1633071600 as Time, open: 4301, high: 4365.75, low: 4260, close: 4343.75 },
  { time: 1633330800 as Time, open: 4349, high: 4362, low: 4267.5, close: 4291.25 },
  { time: 1633417200 as Time, open: 4295.75, high: 4359.75, low: 4269, close: 4334 },
  { time: 1633503600 as Time, open: 4334, high: 4357.5, low: 4273.75, close: 4354 },
  { time: 1633590000 as Time, open: 4355.25, high: 4421.5, low: 4355, close: 4390 },
  { time: 1633676400 as Time, open: 4390.5, high: 4407.75, low: 4376.25, close: 4382.25 },
  { time: 1633935600 as Time, open: 4381, high: 4407.5, low: 4344, close: 4351 },
  { time: 1634022000 as Time, open: 4347.75, high: 4365, low: 4317.25, close: 4340.75 },
  { time: 1634108400 as Time, open: 4327.5, high: 4364.75, low: 4318.75, close: 4355 },
  { time: 1634194800 as Time, open: 4354.75, high: 4437.25, low: 4354, close: 4429 },
  { time: 1634281200 as Time, open: 4433, high: 4467.5, low: 4426.25, close: 4462.5 },
  { time: 1634540400 as Time, open: 4465.5, high: 4479.75, low: 4436.25, close: 4477.5 },
  { time: 1634626800 as Time, open: 4475.75, high: 4517.5, low: 4471.75, close: 4511.25 },
  { time: 1634713200 as Time, open: 4516, high: 4532.25, low: 4504, close: 4528 },
  { time: 1634799600 as Time, open: 4525, high: 4543.25, low: 4510.25, close: 4541.75 },
  { time: 1634886000 as Time, open: 4530, high: 4551.5, low: 4515.25, close: 4536.5 },
  { time: 1635145200 as Time, open: 4528.75, high: 4566.25, low: 4522.5, close: 4558 },
  { time: 1635231600 as Time, open: 4564.75, high: 4590, low: 4560.75, close: 4565.25 },
  { time: 1635318000 as Time, open: 4563.75, high: 4576.75, low: 4543.75, close: 4544.5 },
  { time: 1635404400 as Time, open: 4548.75, high: 4589.75, low: 4545.25, close: 4587.5 },
  { time: 1635490800 as Time, open: 4577, high: 4603.5, low: 4559.25, close: 4597 },
  { time: 1635750000 as Time, open: 4608, high: 4619.5, low: 4586.5, close: 4605.75 },
  { time: 1635836400 as Time, open: 4605.75, high: 4627, low: 4593.25, close: 4623.5 },
  { time: 1635922800 as Time, open: 4621.25, high: 4657, low: 4613, close: 4652.25 },
  { time: 1636009200 as Time, open: 4651.5, high: 4676.25, low: 4650.75, close: 4673.25 },
  { time: 1636095600 as Time, open: 4671.75, high: 4711.75, low: 4667.5, close: 4690.25 },
  { time: 1636358400 as Time, open: 4678.5, high: 4707, low: 4676.25, close: 4694 },
  { time: 1636444800 as Time, open: 4690.75, high: 4700.5, low: 4663.25, close: 4678.25 },
  { time: 1636531200 as Time, open: 4674.75, high: 4680.25, low: 4625.25, close: 4642 },
  { time: 1636617600 as Time, open: 4645, high: 4661.5, low: 4638, close: 4643 },
  { time: 1636704000 as Time, open: 4647, high: 4685.5, low: 4643.75, close: 4678.25 },
  { time: 1636963200 as Time, open: 4684.75, high: 4697.5, low: 4667, close: 4679 },
  { time: 1637049600 as Time, open: 4680.75, high: 4709.75, low: 4670.75, close: 4696 },
  { time: 1637136000 as Time, open: 4696.5, high: 4701, low: 4679.25, close: 4686.25 },
  { time: 1637222400 as Time, open: 4685.25, high: 4706.5, low: 4668, close: 4701.5 },
  { time: 1637308800 as Time, open: 4705.25, high: 4723.5, low: 4684.25, close: 4694.5 },
  { time: 1637568000 as Time, open: 4701, high: 4740.5, low: 4674.25, close: 4679.75 },
  { time: 1637654400 as Time, open: 4686, high: 4695.5, low: 4649, close: 4688.5 },
  { time: 1637740800 as Time, open: 4686.25, high: 4702.25, low: 4656.25, close: 4699 },
  { time: 1637913600 as Time, open: 4700.5, high: 4717, low: 4577.25, close: 4595.75 },
  { time: 1638172800 as Time, open: 4589, high: 4669.75, low: 4588.75, close: 4651 },
  { time: 1638259200 as Time, open: 4657.25, high: 4667.5, low: 4557, close: 4566.25 },
  { time: 1638345600 as Time, open: 4587.5, high: 4650.75, low: 4497.75, close: 4508.5 },
  { time: 1638432000 as Time, open: 4514.75, high: 4593.75, low: 4505.5, close: 4575.75 },
  { time: 1638518400 as Time, open: 4587.25, high: 4606.5, low: 4492, close: 4537.5 },
  { time: 1638777600 as Time, open: 4542.25, high: 4611.75, low: 4531.5, close: 4590 },
  { time: 1638864000 as Time, open: 4594.25, high: 4697.25, low: 4587.25, close: 4685 },
  { time: 1638950400 as Time, open: 4695.25, high: 4712, low: 4671.75, close: 4699 },
  { time: 1639036800 as Time, open: 4697.25, high: 4706, low: 4662.25, close: 4667 },
  { time: 1639123200 as Time, open: 4662.25, high: 4705.25, low: 4657, close: 4703.5 },
  { time: 1639382400 as Time, open: 4704.5, high: 4723.25, low: 4655.5, close: 4659.5 },
  { time: 1639468800 as Time, open: 4663, high: 4676.75, low: 4596.25, close: 4628 },
  { time: 1639555200 as Time, open: 4629, high: 4705.75, low: 4602, close: 4700.5 },
  { time: 1639641600 as Time, open: 4702.75, high: 4743.25, low: 4642, close: 4659.25 },
  { time: 1639728000 as Time, open: 4664, high: 4668, low: 4590, close: 4610 },
  { time: 1639987200 as Time, open: 4612, high: 4621.5, low: 4520.25, close: 4558.5 },
  { time: 1640073600 as Time, open: 4567.75, high: 4643, low: 4565.75, close: 4640.75 },
  { time: 1640160000 as Time, open: 4641.75, high: 4690.5, low: 4622.25, close: 4686 },
  { time: 1640246400 as Time, open: 4689, high: 4731.25, low: 4684.25, close: 4715.75 },
  { time: 1640592000 as Time, open: 4717, high: 4784.25, low: 4713.25, close: 4782.25 },
  { time: 1640678400 as Time, open: 4780.5, high: 4798, low: 4770.5, close: 4778.5 },
  { time: 1640764800 as Time, open: 4781, high: 4796, low: 4770, close: 4784.5 },
  { time: 1640851200 as Time, open: 4784.75, high: 4799.75, low: 4767.25, close: 4772.25 },
  { time: 1640937600 as Time, open: 4773.75, high: 4778.5, low: 4750.5, close: 4758.5 },
  { time: 1641196800 as Time, open: 4771, high: 4791.25, low: 4747.5, close: 4786 },
  { time: 1641283200 as Time, open: 4785.25, high: 4808.25, low: 4764.5, close: 4784.25 },
  { time: 1641369600 as Time, open: 4783.5, high: 4788.25, low: 4689.5, close: 4692.5 },
  { time: 1641456000 as Time, open: 4692, high: 4715.75, low: 4662, close: 4687.5 },
  { time: 1641542400 as Time, open: 4695, high: 4705.75, low: 4653.75, close: 4667.75 },
  { time: 1641801600 as Time, open: 4671.25, high: 4681.75, low: 4572.75, close: 4662.25 },
  { time: 1641888000 as Time, open: 4663.5, high: 4707.5, low: 4627.25, close: 4705 },
  { time: 1641974400 as Time, open: 4704, high: 4739.5, low: 4695, close: 4716.25 },
  { time: 1642060800 as Time, open: 4719.25, high: 4736.25, low: 4642.5, close: 4652 },
  { time: 1642147200 as Time, open: 4655, high: 4667, low: 4606, close: 4654.75 },
  { time: 1642492800 as Time, open: 4666, high: 4671.75, low: 4560, close: 4571.25 },
  { time: 1642579200 as Time, open: 4577.75, high: 4603, low: 4517.25, close: 4524.25 },
  { time: 1642665600 as Time, open: 4526, high: 4594.25, low: 4437.75, close: 4474.75 },
  { time: 1642752000 as Time, open: 4454.25, high: 4487, low: 4381.25, close: 4390 },
  { time: 1643011200 as Time, open: 4389, high: 4427.5, low: 4212.75, close: 4403.75 },
  { time: 1643097600 as Time, open: 4402.75, high: 4406.75, low: 4276.5, close: 4349 },
  { time: 1643184000 as Time, open: 4308.75, high: 4446.25, low: 4294.25, close: 4341.5 },
  { time: 1643270400 as Time, open: 4345.25, high: 4422, low: 4263.25, close: 4317.75 },
  { time: 1643356800 as Time, open: 4348, high: 4426, low: 4266.25, close: 4423.25 },
  { time: 1643616000 as Time, open: 4423.5, high: 4507.75, low: 4395.5, close: 4504.25 },
  { time: 1643702400 as Time, open: 4493.25, high: 4554.75, low: 4474, close: 4535 },
  { time: 1643788800 as Time, open: 4552, high: 4586, low: 4535.25, close: 4577.25 },
  { time: 1643875200 as Time, open: 4545.75, high: 4548.25, low: 4462, close: 4469 },
  { time: 1643961600 as Time, open: 4518, high: 4532.5, low: 4438.5, close: 4492.5 },
  { time: 1644220800 as Time, open: 4497, high: 4514.5, low: 4462.75, close: 4475.75 },
  { time: 1644307200 as Time, open: 4484, high: 4523.75, low: 4456.25, close: 4512.5 },
  { time: 1644393600 as Time, open: 4519, high: 4585, low: 4517.25, close: 4577.75 },
  { time: 1644480000 as Time, open: 4582.25, high: 4583.75, low: 4476, close: 4497.5 },
  { time: 1644566400 as Time, open: 4494.5, high: 4520.5, low: 4393.25, close: 4409.5 },
  { time: 1644825600 as Time, open: 4411.75, high: 4428, low: 4354, close: 4394 },
  { time: 1644912000 as Time, open: 4393.5, high: 4468, low: 4381.75, close: 4464.5 },
  { time: 1644998400 as Time, open: 4458.75, high: 4484.5, low: 4422.75, close: 4470 },
  { time: 1645084800 as Time, open: 4464.25, high: 4474.75, low: 4367.25, close: 4374.5 },
  { time: 1645171200 as Time, open: 4374.75, high: 4411.5, low: 4321, close: 4343.5 },
  { time: 1645516800 as Time, open: 4324.25, high: 4391.25, low: 4250, close: 4300 },
  { time: 1645603200 as Time, open: 4310.75, high: 4345.5, low: 4212.5, close: 4222 },
  { time: 1645689600 as Time, open: 4215.5, high: 4290, low: 4101.75, close: 4284 },
  { time: 1645776000 as Time, open: 4266.75, high: 4384.25, low: 4227.5, close: 4380 },
  { time: 1646035200 as Time, open: 4299.5, high: 4385.5, low: 4251.5, close: 4368 },
  { time: 1646121600 as Time, open: 4367.5, high: 4399, low: 4275, close: 4303.75 },
  { time: 1646208000 as Time, open: 4308.75, high: 4399.25, low: 4278.25, close: 4381.75 },
  { time: 1646294400 as Time, open: 4373.75, high: 4418.75, low: 4341, close: 4359.25 },
  { time: 1646380800 as Time, open: 4366.5, high: 4374.5, low: 4281.25, close: 4327.25 },
  { time: 1646640000 as Time, open: 4308.75, high: 4325.25, low: 4185.25, close: 4198.5 },
  { time: 1646726400 as Time, open: 4186.5, high: 4275, low: 4138.75, close: 4168.75 },
  { time: 1646812800 as Time, open: 4153, high: 4298.25, low: 4152, close: 4275.25 },
  { time: 1646899200 as Time, open: 4279, high: 4282.25, low: 4207, close: 4257.25 },
  { time: 1646985600 as Time, open: 4248.75, high: 4326.75, low: 4189, close: 4192.5 },
  { time: 1647241200 as Time, open: 4206.75, high: 4244.75, low: 4152.25, close: 4163.5 },
  { time: 1647327600 as Time, open: 4171.25, high: 4263.25, low: 4129.5, close: 4253.75 },
  { time: 1647414000 as Time, open: 4249.75, high: 4367.5, low: 4239, close: 4349.5 },
  { time: 1647500400 as Time, open: 4361, high: 4406.75, low: 4320.25, close: 4402 },
  { time: 1647586800 as Time, open: 4384.25, high: 4465.75, low: 4364.5, close: 4453.5 },
  { time: 1647846000 as Time, open: 4460, high: 4473, low: 4415, close: 4452.25 },
  { time: 1647932400 as Time, open: 4456.75, high: 4514.75, low: 4433, close: 4505 },
  { time: 1648018800 as Time, open: 4504, high: 4514, low: 4444.75, close: 4447.5 },
  { time: 1648105200 as Time, open: 4449.25, high: 4517.5, low: 4445.75, close: 4512.5 },
  { time: 1648191600 as Time, open: 4516.25, high: 4539, low: 4493.25, close: 4536.5 },
  { time: 1648450800 as Time, open: 4535.25, high: 4572.25, low: 4509.75, close: 4568 },
  { time: 1648537200 as Time, open: 4570.25, high: 4631, low: 4565.25, close: 4625.5 },
  { time: 1648623600 as Time, open: 4621.25, high: 4627.5, low: 4574.75, close: 4596 },
  { time: 1648710000 as Time, open: 4599, high: 4614.25, low: 4526.25, close: 4530.75 },
  { time: 1648796400 as Time, open: 4541, high: 4555.5, low: 4501.25, close: 4539.25 },
  { time: 1649055600 as Time, open: 4538.25, high: 4580, low: 4527.75, close: 4577.75 },
  { time: 1649142000 as Time, open: 4576.25, high: 4588.75, low: 4507.75, close: 4520.25 },
  { time: 1649228400 as Time, open: 4526.25, high: 4528.75, low: 4444.5, close: 4475.75 },
  { time: 1649314800 as Time, open: 4471.25, high: 4517.25, low: 4444.5, close: 4496.25 },
  { time: 1649401200 as Time, open: 4494.75, high: 4519.75, low: 4468.75, close: 4483.5 },
  { time: 1649660400 as Time, open: 4488.75, high: 4491.25, low: 4403.5, close: 4409 },
  { time: 1649746800 as Time, open: 4411, high: 4466.75, low: 4375.5, close: 4393 },
  { time: 1649833200 as Time, open: 4396.75, high: 4449.5, low: 4384, close: 4442.25 },
  { time: 1649919600 as Time, open: 4438.5, high: 4455.75, low: 4385, close: 4387.5 },
  { time: 1650265200 as Time, open: 4390, high: 4406.25, low: 4355.5, close: 4386.75 },
  { time: 1650351600 as Time, open: 4399, high: 4467, low: 4371.75, close: 4459.25 },
  { time: 1650438000 as Time, open: 4441, high: 4484.25, low: 4432.75, close: 4455.5 },
  { time: 1650524400 as Time, open: 4468, high: 4509, low: 4380, close: 4390.5 },
  { time: 1650610800 as Time, open: 4385.75, high: 4393.25, low: 4247.5, close: 4267.25 },
  { time: 1650870000 as Time, open: 4259, high: 4296.5, low: 4195.25, close: 4292.75 },
  { time: 1650956400 as Time, open: 4294, high: 4303.5, low: 4136.75, close: 4170.5 },
  { time: 1651042800 as Time, open: 4149.5, high: 4236.25, low: 4149, close: 4180.25 },
  { time: 1651129200 as Time, open: 4213, high: 4303.5, low: 4182.5, close: 4283.5 },
  { time: 1651215600 as Time, open: 4244, high: 4279.75, low: 4118.75, close: 4127.5 },
];

// Leg definitions based on actual ES market structure May 2021 - April 2022
interface PreviewLeg {
  id: string;
  direction: 'bull' | 'bear';
  originTime: number;
  originPrice: number;
  pivotTime: number;
  pivotPrice: number;
  label: string;
}

const PREVIEW_LEGS: PreviewLeg[] = [
  {
    id: 'bull-1',
    direction: 'bull',
    originTime: 1620889200,   // May 13, 2021 - swing low
    originPrice: 4029.25,
    pivotTime: 1641283200,    // Jan 4, 2022 - ATH
    pivotPrice: 4808.25,
    label: 'Bull Run to ATH',
  },
  {
    id: 'bear-1',
    direction: 'bear',
    originTime: 1641283200,   // Jan 4, 2022 - ATH
    originPrice: 4808.25,
    pivotTime: 1645689600,    // Feb 24, 2022 - correction low
    pivotPrice: 4101.75,
    label: 'Correction',
  },
  {
    id: 'bull-2',
    direction: 'bull',
    originTime: 1645689600,   // Feb 24, 2022
    originPrice: 4101.75,
    pivotTime: 1648537200,    // Mar 29, 2022 - bounce high
    pivotPrice: 4631,
    label: 'Recovery Rally',
  },
];

// Fib ratios to display
const FIB_RATIOS = [0.382, 0.618, 1.0, 1.618];

// Compute fib levels for a leg
const computeFibLevels = (leg: PreviewLeg): { ratio: number; price: number }[] => {
  const origin = leg.originPrice;
  const pivot = leg.pivotPrice;

  return FIB_RATIOS.map(ratio => {
    // For fib levels: 0 = origin, 1 = pivot
    // price = origin + ratio * (pivot - origin)
    const price = origin + ratio * (pivot - origin);
    return { ratio, price };
  });
};

export const MarketChartPreview: React.FC = () => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const legSeriesRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map());
  const fibSeriesRef = useRef<Map<string, ISeriesApi<'Line'>>>(new Map());

  const [hoveredLeg, setHoveredLeg] = useState<PreviewLeg | null>(null);
  const [isChartReady, setIsChartReady] = useState(false);

  // Get leg pixel positions for hover detection
  const getLegPositions = useCallback(() => {
    if (!chartRef.current || !candleSeriesRef.current) return [];

    const chart = chartRef.current;
    const series = candleSeriesRef.current;
    const timeScale = chart.timeScale();

    return PREVIEW_LEGS.map(leg => {
      const originX = timeScale.timeToCoordinate(leg.originTime as Time);
      const originY = series.priceToCoordinate(leg.originPrice);
      const pivotX = timeScale.timeToCoordinate(leg.pivotTime as Time);
      const pivotY = series.priceToCoordinate(leg.pivotPrice);

      return {
        leg,
        originX: originX ?? 0,
        originY: originY ?? 0,
        pivotX: pivotX ?? 0,
        pivotY: pivotY ?? 0,
      };
    });
  }, []);

  // Distance from point to line segment
  const distanceToLineSegment = (
    px: number, py: number,
    x1: number, y1: number,
    x2: number, y2: number
  ): number => {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const lengthSq = dx * dx + dy * dy;

    if (lengthSq === 0) {
      return Math.sqrt((px - x1) ** 2 + (py - y1) ** 2);
    }

    let t = ((px - x1) * dx + (py - y1) * dy) / lengthSq;
    t = Math.max(0, Math.min(1, t));

    const projX = x1 + t * dx;
    const projY = y1 + t * dy;

    return Math.sqrt((px - projX) ** 2 + (py - projY) ** 2);
  };

  // Find nearest leg to mouse position
  const findNearestLeg = useCallback((x: number, y: number): PreviewLeg | null => {
    const positions = getLegPositions();
    const THRESHOLD = 20; // pixels

    let nearestLeg: PreviewLeg | null = null;
    let nearestDistance = Infinity;

    for (const pos of positions) {
      const distance = distanceToLineSegment(
        x, y,
        pos.originX, pos.originY,
        pos.pivotX, pos.pivotY
      );

      if (distance < nearestDistance && distance <= THRESHOLD) {
        nearestDistance = distance;
        nearestLeg = pos.leg;
      }
    }

    return nearestLeg;
  }, [getLegPositions]);

  // Create leg line series
  const createLegLine = useCallback((
    chart: IChartApi,
    leg: PreviewLeg,
    isHighlighted: boolean
  ): ISeriesApi<'Line'> => {
    const color = leg.direction === 'bull' ? '#22c55e' : '#ef4444';
    const opacity = isHighlighted ? 1.0 : 0.7;
    const lineWidth = isHighlighted ? 3 : 2;

    const r = parseInt(color.slice(1, 3), 16);
    const g = parseInt(color.slice(3, 5), 16);
    const b = parseInt(color.slice(5, 7), 16);

    const lineSeries = chart.addSeries(LineSeries, {
      color: `rgba(${r}, ${g}, ${b}, ${opacity})`,
      lineWidth: lineWidth as LineWidth,
      lineStyle: LineStyle.Solid,
      crosshairMarkerVisible: false,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    const data: LineData<Time>[] = [
      { time: leg.originTime as Time, value: leg.originPrice },
      { time: leg.pivotTime as Time, value: leg.pivotPrice },
    ];
    data.sort((a, b) => (a.time as number) - (b.time as number));

    lineSeries.setData(data);
    return lineSeries;
  }, []);

  // Create fib level lines for a leg
  const createFibLines = useCallback((
    chart: IChartApi,
    leg: PreviewLeg
  ): ISeriesApi<'Line'>[] => {
    const color = leg.direction === 'bull' ? '#22c55e' : '#ef4444';
    const fibLevels = computeFibLevels(leg);
    const series: ISeriesApi<'Line'>[] = [];

    // Get visible time range
    const firstTime = PREVIEW_OHLC_DATA[0].time as number;
    const lastTime = PREVIEW_OHLC_DATA[PREVIEW_OHLC_DATA.length - 1].time as number;

    for (const { price } of fibLevels) {
      const r = parseInt(color.slice(1, 3), 16);
      const g = parseInt(color.slice(3, 5), 16);
      const b = parseInt(color.slice(5, 7), 16);

      const fibSeries = chart.addSeries(LineSeries, {
        color: `rgba(${r}, ${g}, ${b}, 0.4)`,
        lineWidth: 1 as LineWidth,
        lineStyle: LineStyle.Dashed,
        crosshairMarkerVisible: false,
        priceLineVisible: false,
        lastValueVisible: false,
        // Prevent fib lines from affecting auto-scale
        autoscaleInfoProvider: () => null,
      });

      const data: LineData<Time>[] = [
        { time: firstTime as Time, value: price },
        { time: lastTime as Time, value: price },
      ];

      fibSeries.setData(data);
      series.push(fibSeries);
    }

    return series;
  }, []);

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0f172a' },
        textColor: '#64748b',
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight,
      timeScale: {
        timeVisible: false,
        borderColor: '#334155',
        visible: false, // Hide time scale for cleaner preview
      },
      rightPriceScale: {
        borderColor: '#334155',
        visible: false, // Hide price scale for cleaner preview
      },
      crosshair: {
        vertLine: { visible: false },
        horzLine: { visible: false },
      },
      handleScroll: false,
      handleScale: false,
    });
    chartRef.current = chart;

    // Create candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    });
    candleSeriesRef.current = candleSeries;
    candleSeries.setData(PREVIEW_OHLC_DATA);

    // Create leg lines
    for (const leg of PREVIEW_LEGS) {
      const lineSeries = createLegLine(chart, leg, false);
      legSeriesRef.current.set(leg.id, lineSeries);
    }

    // Fit content with some padding
    chart.timeScale().fitContent();

    setIsChartReady(true);

    // Resize handler
    const resizeObserver = new ResizeObserver(() => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    });
    resizeObserver.observe(chartContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      legSeriesRef.current.clear();
      fibSeriesRef.current.clear();
      setIsChartReady(false);
    };
  }, [createLegLine]);

  // Update leg highlighting on hover
  useEffect(() => {
    if (!chartRef.current || !isChartReady) return;

    const chart = chartRef.current;

    // Clear existing leg series
    for (const [, series] of legSeriesRef.current) {
      try {
        chart.removeSeries(series);
      } catch {
        // Series may already be removed
      }
    }
    legSeriesRef.current.clear();

    // Clear existing fib series
    for (const [, series] of fibSeriesRef.current) {
      try {
        chart.removeSeries(series);
      } catch {
        // Series may already be removed
      }
    }
    fibSeriesRef.current.clear();

    // Recreate leg lines with proper highlighting
    for (const leg of PREVIEW_LEGS) {
      const isHighlighted = hoveredLeg?.id === leg.id;
      const lineSeries = createLegLine(chart, leg, isHighlighted);
      legSeriesRef.current.set(leg.id, lineSeries);
    }

    // Create fib lines for hovered leg
    if (hoveredLeg) {
      const fibLines = createFibLines(chart, hoveredLeg);
      fibLines.forEach((series, i) => {
        fibSeriesRef.current.set(`${hoveredLeg.id}_fib_${i}`, series);
      });
    }
  }, [hoveredLeg, isChartReady, createLegLine, createFibLines]);

  // Mouse move handler for hover detection
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!chartContainerRef.current || !isChartReady) return;

    const rect = chartContainerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const nearestLeg = findNearestLeg(x, y);
    setHoveredLeg(nearestLeg);
  }, [isChartReady, findNearestLeg]);

  const handleMouseLeave = useCallback(() => {
    setHoveredLeg(null);
  }, []);

  // Compute fib label positions for overlay
  const getFibLabelPositions = useCallback(() => {
    if (!hoveredLeg || !chartRef.current || !candleSeriesRef.current) return [];

    const series = candleSeriesRef.current;
    const fibLevels = computeFibLevels(hoveredLeg);

    return fibLevels.map(({ ratio, price }) => {
      const y = series.priceToCoordinate(price);
      return { ratio, y: y ?? 0 };
    }).filter(p => p.y !== 0);
  }, [hoveredLeg]);

  return (
    <div className="w-full rounded-2xl overflow-hidden shadow-2xl shadow-cyan-500/10 border border-white/10 relative">
      <div
        ref={chartContainerRef}
        className="w-full aspect-[16/9] bg-slate-900"
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      />

      {/* Fib level labels overlay */}
      {hoveredLeg && isChartReady && (
        <div className="absolute inset-0 pointer-events-none">
          {getFibLabelPositions().map(({ ratio, y }) => (
            <div
              key={ratio}
              className="absolute left-2 transform -translate-y-1/2"
              style={{ top: y }}
            >
              <span
                className={`text-xs font-mono px-1.5 py-0.5 rounded ${
                  hoveredLeg.direction === 'bull'
                    ? 'bg-green-500/20 text-green-400'
                    : 'bg-red-500/20 text-red-400'
                }`}
              >
                {ratio.toFixed(3)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Leg info tooltip */}
      {hoveredLeg && (
        <div className="absolute bottom-4 left-4 bg-slate-800/90 backdrop-blur border border-white/10 rounded-lg px-3 py-2 pointer-events-none">
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                hoveredLeg.direction === 'bull' ? 'bg-green-500' : 'bg-red-500'
              }`}
            />
            <span className="text-sm font-medium text-white">{hoveredLeg.label}</span>
          </div>
          <div className="text-xs text-slate-400 mt-1">
            {hoveredLeg.originPrice.toFixed(2)} → {hoveredLeg.pivotPrice.toFixed(2)}
          </div>
        </div>
      )}

      {/* Subtle instruction hint */}
      {!hoveredLeg && isChartReady && (
        <div className="absolute bottom-4 right-4 text-xs text-slate-500 pointer-events-none">
          Hover legs for Fibonacci levels
        </div>
      )}
    </div>
  );
};
